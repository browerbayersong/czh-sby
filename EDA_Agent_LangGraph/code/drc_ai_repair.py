"""DeepSeek + LangGraph DRC repair on disposable copies of one recorded ICC case.

The model chooses structured, bounded routing operations; it never supplies shell
commands or unchecked Tcl. Only actual ICC reports decide acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import TypedDict, Any
from datetime import datetime
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage
from first_do import build_llm
from eda_backend_analysis import parse_routing_drc, parse_pg_connectivity, parse_lvs

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'designs/counter_backend'
QUEUE = BASE / 'session_queue'
SOURCE_RUN = 'upload_20261025_143839_f96edb1f'
SOURCE_MW = '/home/IC/Desktop/EDA_Projects/counter_backend/runs/' + SOURCE_RUN + '/build/icc/counter_mw'
STRATEGIES = {'ripup_pair', 'ripup_n7', 'ripup_count5', 'move_u14'}
TAPERS = {'default_width', 'pin_width', 'off'}


class QueueClient:
    def __init__(self, queue=QUEUE):
        self.queue = queue
        status = json.loads((queue / 'session_status.json').read_text(encoding='utf-8'))
        if status.get('status') != 'connected':
            raise RuntimeError('请先启动 backend_session.py --fresh-session')
        self.session = status['session']

    def send(self, action: dict, timeout=120) -> tuple[dict, Path]:
        status = json.loads((self.queue/'session_status.json').read_text(encoding='utf-8'))
        if status.get('session') != self.session or status.get('status') != 'connected':
            raise RuntimeError('后端会话已经变更或结束，停止下发任务')
        n = max([int(p.stem.split('_')[1]) for p in self.queue.glob('request_*.json')] + [0]) + 1
        request = self.queue / f'request_{n:03}.json'
        with request.open('x', encoding='utf-8') as f:
            json.dump(action, f, ensure_ascii=False)
        folder = self.queue / f'result_{n:03}'
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(.5)
                continue
            if result.get('status') != 'completed':
                raise RuntimeError(f'任务 {n} 失败：{result.get("error")}')
            return result, folder
        raise TimeoutError(f'任务 {n} 等待超时；停止图流程，不自动重复运行')

    def run(self, script: str) -> tuple[str, Path]:
        record, _ = self.send({'action':'start_run'}, 200)
        run = record['run_label']
        self.send({'action':'launch_tool','run':run,'tool':'icc','script':script,'timeout':180}, 40)
        deadline = time.monotonic() + 215
        while time.monotonic() < deadline:
            time.sleep(3)
            result, folder = self.send({'action':'fetch','run':run,'paths':['build/icc.status.json']}, 35)
            status_path = folder/'build/icc.status.json'
            if status_path.is_file():
                status = json.loads(status_path.read_text())
                if status.get('state') == 'exited':
                    break
        else:
            raise TimeoutError('ICC 未在期限内返回；先诊断，不继续启动新轮次')
        paths = ['build/icc.log','build/icc.status.json'] + [
            'build/drc_ai/'+name for name in ('before_drc.rpt','routing_drc.rpt',
            'pg_connectivity.rpt','lvs.rpt','placement_legality.rpt','netlist_before.v',
            'netlist_after.v','cell_inventory_before.txt','cell_inventory_after.txt',
            'counter_8bit.routed.v','counter_8bit.sdc','counter_8bit.gds','drc_details.txt')]
        _, folder = self.send({'action':'fetch','run':run,'paths':paths}, 60)
        return run, folder


def validate_plan(plan: dict) -> dict:
    if not isinstance(plan, dict) or plan.get('strategy') not in STRATEGIES:
        raise ValueError('模型策略不在允许集合中')
    if plan.get('pin_taper_mode') not in TAPERS:
        raise ValueError('非法 pin_taper_mode')
    if type(plan.get('extra_pin_tracks')) is not bool:
        raise ValueError('extra_pin_tracks 必须为布尔值')
    if not isinstance(plan.get('diagnosis'), str) or not plan['diagnosis'].strip():
        raise ValueError('必须记录模型诊断')
    if plan['strategy'] == 'move_u14':
        if type(plan.get('dx')) not in (float,int) or plan['dx'] not in (-1.12,-.56,.56,1.12):
            raise ValueError('只允许 U14 以已知 0.28um 站点的倍数局部移动')
    allowed = {'strategy','pin_taper_mode','extra_pin_tracks','diagnosis','expected_effect','dx'}
    if set(plan) - allowed:
        raise ValueError('模型输出含未声明字段')
    return plan


def render_tcl(plan: dict) -> str:
    validate_plan(plan)
    extra = 'true' if plan['extra_pin_tracks'] else 'false'
    operation = 'remove_net_routing $selected'
    if plan['strategy'] == 'ripup_n7':
        operation = 'remove_net_routing $n7'
    elif plan['strategy'] == 'ripup_count5':
        operation = 'remove_net_routing $c5'
    elif plan['strategy'] == 'move_u14':
        operation = ('set touched [get_nets -of_objects [get_pins -of_objects [get_cells U14]]]\n'
            'remove_net_routing $touched\n'
            f'move_objects -delta {{{plan["dx"]} 0}} [get_cells U14]\n'
            'legalize_placement -cells [get_cells U14] -effort high\n'
            'set selected $touched')
    return r'''source generated/scripts/config.tcl
set_app_var target_library [list $EDA_DB]
set_app_var synthetic_library [list standard.sldb]
set_app_var link_library [concat [list *] [list $EDA_DB]]
set_host_options -max_cores 1
file mkdir ../build/drc_ai
proc inventory {filename} {
    set h [open $filename w]
    set rows {}
    foreach_in_collection c [get_cells -hierarchical *] {
        lappend rows "[get_object_name $c] [get_attribute $c ref_name]"
    }
    foreach row [lsort $rows] {puts $h $row}
    close $h
}
if {[catch {
    copy_mw_lib -from @SOURCE@ -to ../build/drc_ai/counter_mw
    open_mw_lib ../build/drc_ai/counter_mw
    open_mw_cel counter_8bit
    redirect -file ../build/drc_ai/before_drc.rpt {verify_zrt_route -drc true -open_net true}
    write_verilog -no_physical_only_cells ../build/drc_ai/netlist_before.v
    inventory ../build/drc_ai/cell_inventory_before.txt
    set n7 ""
    set c5 ""
    foreach_in_collection n [get_nets -hierarchical *] {
        set canonical [string map [list "\\" ""] [get_object_name $n]]
        if {$canonical eq {N7}} {set n7 $n}
        if {$canonical eq {count[5]}} {set c5 $n}
    }
    set selected [add_to_collection $n7 $c5]
    if {[sizeof_collection $selected] != 2} {error "Target nets do not match recorded case"}
    set_route_zrt_detail_options -drc_convergence_effort_level high -pin_taper_mode @TAPER@ -generate_extra_off_grid_pin_tracks @EXTRA@
    @OPERATION@
    route_zrt_eco -nets $selected -reroute modified_nets_first_then_others -utilize_dangling_wires false -max_detail_route_iterations 80
    redirect -file ../build/drc_ai/routing_drc.rpt {verify_zrt_route -drc true -open_net true}
    redirect -file ../build/drc_ai/pg_connectivity.rpt {verify_pg_nets}
    redirect -file ../build/drc_ai/lvs.rpt {verify_lvs}
    redirect -file ../build/drc_ai/placement_legality.rpt {check_legality -verbose}
    set h [open ../build/drc_ai/drc_details.txt w]
    foreach_in_collection item [get_drc_errors -quiet] {
        foreach attr {type bbox layer_names net1_name net2_name} {
            puts $h "$attr: [get_attribute $item $attr]"
        }
    }
    close $h
    write_verilog -no_physical_only_cells ../build/drc_ai/netlist_after.v
    inventory ../build/drc_ai/cell_inventory_after.txt
    save_mw_cel
    write_verilog -no_physical_only_cells ../build/drc_ai/counter_8bit.routed.v
    write_sdc -nosplit ../build/drc_ai/counter_8bit.sdc
    set_write_stream_options -map_layer $EDA_GDS_MAP
    write_stream -format gds -cells $EDA_TOP ../build/drc_ai/counter_8bit.gds
    puts "EDA_DRC_AI_CANDIDATE_EXECUTED"
} message]} {puts "EDA_DRC_AI_FATAL $message"; exit 2}
exit 0
'''.replace('@SOURCE@',SOURCE_MW).replace('@TAPER@',plan['pin_taper_mode']).replace('@EXTRA@',extra).replace('@OPERATION@',operation)


def read_file(path):
    return path.read_text(encoding='utf-8', errors='replace') if path.is_file() else ''


def canonical_netlist(text: str) -> str:
    # Exclude timestamps and generator comments; retain actual Verilog tokens.
    text = re.sub(r'/\*.*?\*/','',text,flags=re.S)
    text = re.sub(r'//[^\n]*','',text)
    return re.sub(r'\s+',' ',text).strip()


def evaluate(folder: Path) -> dict:
    d=folder/'build/drc_ai'
    status=json.loads(read_file(folder/'build/icc.status.json'))
    routing=parse_routing_drc(read_file(d/'routing_drc.rpt'))
    pg=parse_pg_connectivity(read_file(d/'pg_connectivity.rpt'))
    lvs=parse_lvs(read_file(d/'lvs.rpt'))
    before=canonical_netlist(read_file(d/'netlist_before.v'))
    after=canonical_netlist(read_file(d/'netlist_after.v'))
    unchanged=bool(before) and before==after
    inventory=read_file(d/'cell_inventory_before.txt')
    inventory_equal=bool(inventory) and inventory==read_file(d/'cell_inventory_after.txt')
    legality=read_file(d/'placement_legality.rpt')
    # Require all six fixed and all six non-fixed counts in this ICC version.
    labels=('Cells Not on Row','Cell Overlaps','Cells overlapping blockages',
            'Orientation Violations','Site Violations','Power Strap Violations')
    legal_counts=[]
    for label in labels:
        fixed=re.search(r'(?im)^\(fixed placement\)\s*'+re.escape(label)+r'\s*:\s*(\d+)',legality)
        movable=re.search(r'(?im)^Number of '+re.escape(label)+r'\s*:\s*(\d+)',legality)
        legal_counts += [int(x[1]) if x else None for x in (fixed,movable)]
    legality_ok=all(x==0 for x in legal_counts)
    before_routing=parse_routing_drc(read_file(d/'before_drc.rpt'))
    baseline_ok=(before_routing['routing_drc_errors']==1 and before_routing['nets_checked']==36
                 and before_routing['open_nets']==0 and before_routing['unplaced_cells']==0)
    log=read_file(folder/'build/icc.log')
    execution_ok=(re.search(r'(?m)^EDA_DRC_AI_CANDIDATE_EXECUTED\s*$',log) is not None
                  and re.search(r'(?im)^\s*(?:Error:|EDA_DRC_AI_FATAL)',log) is None)
    exports_ok=all((d/name).is_file() and (d/name).stat().st_size>0
                   for name in ('counter_8bit.routed.v','counter_8bit.sdc','counter_8bit.gds'))
    result={'tool_exit_code':status.get('tool_exit_code'),'routing':routing,'pg':pg,'lvs':lvs,
            'netlist_unchanged':unchanged,'cell_inventory_unchanged':inventory_equal,
            'placement_legal':legality_ok,'placement_error_counts':legal_counts,
            'baseline_reproduced':baseline_ok,'execution_completed':execution_ok,
            'exported_artifacts_present':exports_ok,
            'details':read_file(d/'drc_details.txt')[:6000]}
    result['accepted']=(status.get('tool_exit_code')==0 and routing['routing_clean'] is True
        and pg['clean'] is True and lvs['clean'] is True and unchanged and inventory_equal
        and legality_ok and baseline_ok and execution_ok and exports_ok)
    return result


class RepairState(TypedDict, total=False):
    iteration: int
    plan: dict
    result: dict
    history: list
    run: str
    folder: str


def run_graph(context: str, output: Path, max_rounds=4, client=None, model=None):
    output.mkdir(parents=True,exist_ok=False)
    client=client or QueueClient()
    model=model or build_llm()
    system='''你是 Synopsys ICC 2016 物理设计诊断助手。处理一个真实 M1 Diff net spacing。
只输出一个 JSON 对象，字段 strategy, pin_taper_mode, extra_pin_tracks, diagnosis, expected_effect，可选 dx。
strategy 只能 ripup_pair/ripup_n7/ripup_count5/move_u14；pin_taper_mode 只能 default_width/pin_width/off；extra_pin_tracks 为布尔值。
move_u14 只能水平 dx=-1.12,-0.56,0.56,1.12 um，之后工具会合法化并重布其连接网络。
其余策略完整拆除相应目标网络的信号布线再 ECO。不要重复此前失败方案。
本流程不接受任意 Tcl，不降低间距规则、不忽略 DRC、不删标记、不修改 RTL、不编辑工艺库。
不要声称修复通过，成功只能由后续工具报告确认。请基于给定真实证据解释诊断和预期作用。'''
    (output/'system_prompt.txt').write_text(system,encoding='utf-8')
    (output/'context.txt').write_text(context,encoding='utf-8')
    def diagnose(state):
        iteration=state.get('iteration',0)+1
        request=context+'\n实际已尝试的候选及验证结果：\n'+json.dumps(state.get('history',[]),ensure_ascii=False)
        messages=[SystemMessage(content=system),HumanMessage(content=request)]
        response=model.invoke(messages)
        raw=response.content
        (output/f'round_{iteration:02}_request.txt').write_text(request,encoding='utf-8')
        (output/f'round_{iteration:02}_response.txt').write_text(str(raw),encoding='utf-8')
        text=str(raw).strip()
        if text.startswith('```'): text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
        plan=validate_plan(json.loads(text))
        for item in state.get('history',[]):
            if all(item['plan'].get(k)==plan.get(k) for k in ('strategy','pin_taper_mode','extra_pin_tracks','dx')):
                raise ValueError('模型重复了已执行的候选，终止而非重复工具运行')
        (output/f'round_{iteration:02}_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        metadata={'id':getattr(response,'id',None),'usage':getattr(response,'usage_metadata',None),
                  'response_metadata':getattr(response,'response_metadata',{})}
        (output/f'round_{iteration:02}_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(f'第 {iteration} 轮 DeepSeek 选择：{plan["strategy"]} / taper={plan["pin_taper_mode"]}',flush=True)
        return {'iteration':iteration,'plan':plan}
    def execute(state):
        script=render_tcl(state['plan'])
        name=f'drc_ai_candidate_{output.name}_{state["iteration"]:02}.tcl'
        (BASE/'generated/scripts'/name).write_text(script,encoding='utf-8')
        (output/name).write_text(script,encoding='utf-8')
        run,folder=client.run('generated/scripts/'+name)
        return {'run':run,'folder':str(folder)}
    def verify(state):
        result=evaluate(Path(state['folder']))
        record={'iteration':state['iteration'],'plan':state['plan'],'run':state['run'],
                'local_result_folder':state['folder'],'verification':result}
        history=state.get('history',[])+[record]
        (output/'history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'实际 DRC={result["routing"]["routing_drc_errors"]}，验收={result["accepted"]}',flush=True)
        return {'result':result,'history':history}
    graph=StateGraph(RepairState)
    graph.add_node('diagnose_and_propose',diagnose)
    graph.add_node('execute_copy',execute)
    graph.add_node('verify_actual_reports',verify)
    graph.add_edge(START,'diagnose_and_propose')
    graph.add_edge('diagnose_and_propose','execute_copy')
    graph.add_edge('execute_copy','verify_actual_reports')
    graph.add_conditional_edges('verify_actual_reports',lambda s: 'done' if s['result']['accepted'] or s['iteration']>=max_rounds else 'retry',
                                {'done':END,'retry':'diagnose_and_propose'})
    compiled=graph.compile()
    (output/'workflow.mmd').write_text(compiled.get_graph().draw_mermaid(),encoding='utf-8')
    final=compiled.invoke({'iteration':0,'history':[]},{'recursion_limit':max_rounds*4+4})
    (output/'final.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
    return final


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--context',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,choices=range(1,7),default=4)
    args=parser.parse_args()
    run_graph(args.context.read_text(encoding='utf-8'),args.output,args.rounds)


if __name__=='__main__':main()
