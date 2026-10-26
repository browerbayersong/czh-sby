r"""EDA 智能助手 · 每段对话一个独立文件夹（从已验证的旧 Streamlit 页面升级）。

存储结构：<EDA_DATA_DIR>\conversations\<可读对话标题>__<短ID>\chat.json
对话文件夹本身预留为该会话未来的 EDA 工作空间。
保留旧版 conversations.json 和 conversations/<32位ID>.json，不删除、不覆盖。
已有数据采用按 ID 合并；独立文件夹中的 chat.json 为最新权威副本。
"""

import json
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime

import streamlit as st
import difflib
import io
import zipfile
from eda_agent_v8_core import run_task, safe_rel_name, MAX_DRAFT_BYTES, ALLOWED_EXT, SPECIAL_NAMES
from eda_remote_v8 import SSHSettings, RemoteError, connection_probe, file_preview, remote_job


# ==================================
# 1. 本地聊天记录与每会话文件夹
# ==================================

import re

LEGACY_DATA_DIR = Path(r"C:\LangGraph_talk")
DEFAULT_DATA_DIR = (LEGACY_DATA_DIR if LEGACY_DATA_DIR.is_dir()
                    else Path(__file__).resolve().parent.parent / "data")
DATA_DIR = Path(os.getenv("EDA_DATA_DIR") or DEFAULT_DATA_DIR).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "conversations.json"     # 最初的单文件数据库，仅作为迁移来源
CHAT_DIR = DATA_DIR / "conversations"         # 存放旧独立 JSON 和新对话文件夹
OLD_FILE = Path(r"C:\LangGraph\data\chat_history.json")
CHAT_JSON = "chat.json"                      # 每段会话文件夹里固定的 JSON 文件名
VALID_ID = re.compile(r"^[0-9a-f]{32}$")
WINDOWS_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)


def now():
    return datetime.now().isoformat(timespec="seconds")


def create_chat(title="新对话"):
    return {
        "id": uuid4().hex,
        "title": title,
        "messages": [],
        "created_at": now(),
        "updated_at": now(),
        "auto_title": True,
    }


def check_chat_id(chat_id):
    if not isinstance(chat_id, str) or not VALID_ID.fullmatch(chat_id):
        raise ValueError(f"对话 ID 不合法：{chat_id!r}")


def safe_title_part(title):
    """只影响文件夹名称，聊天标题原文不会被修改。"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(title or '新对话'))
    name = re.sub(r'\s+', ' ', name).strip(' ._')
    name = name[:48].rstrip(' ._') or '新对话'
    if WINDOWS_RESERVED.fullmatch(name):
        name = '_' + name
    return name


def folder_is_safe(folder_name):
    """文件夹名来自本地或 JSON，永远不能包含目录跳转。"""
    return (
        isinstance(folder_name, str)
        and folder_name not in {'.', '..'}
        and folder_name == Path(folder_name).name
        and folder_name.strip(' .') != ''
        and not folder_name.endswith((' ', '.'))
        and not re.search(r'[<>:"/\\|?*\x00-\x1f]', folder_name)
        and len(folder_name) <= 160
        and not WINDOWS_RESERVED.fullmatch(folder_name)
    )


def chat_folder_by_name(folder_name):
    if not folder_is_safe(folder_name):
        raise ValueError(f"不安全的会话文件夹名称：{folder_name!r}")
    root = CHAT_DIR.resolve()
    folder = CHAT_DIR / folder_name
    if folder.is_symlink() or (folder.exists() and not folder.resolve().is_relative_to(root)):
        raise PermissionError("拒绝使用指向对话目录之外的文件夹")
    return folder


def choose_folder_name(title, chat_id, current_name=None):
    """可读标题 + 短 ID；重名时加序号。"""
    check_chat_id(chat_id)
    base = safe_title_part(title)
    for number in range(1, 10000):
        tail = f"__{chat_id[:8]}" if number == 1 else f"__{chat_id[:8]}_{number}"
        candidate = base + tail
        path = chat_folder_by_name(candidate)
        if candidate == current_name or not path.exists():
            return candidate
        # 同一个 ID 重跑时可以继续使用已有目录，避免重复创建。
        chat_json = path / CHAT_JSON
        if chat_json.is_file():
            try:
                if json.loads(chat_json.read_text('utf-8')).get('id') == chat_id:
                    return candidate
            except (OSError, ValueError, TypeError):
                pass
    raise FileExistsError("创建对话目录失败：同名冲突太多")


def ensure_chat_folder(chat):
    """为未迁移对话建立文件夹，已有文件夹绝不根据模型输出任意更改路径。"""
    check_chat_id(chat['id'])
    name = chat.get('folder')
    if not name:
        name = choose_folder_name(chat.get('title', '新对话'), chat['id'])
    folder = chat_folder_by_name(name)
    folder.mkdir(parents=True, exist_ok=True)
    if folder.resolve().parent != CHAT_DIR.resolve():
        raise PermissionError("目标工作空间不在对话根目录内")
    chat['folder'] = name
    return folder


def rename_chat_folder(chat, proposed_title):
    """重命名对话时同步重命名物理文件夹，不修改工作空间里的其他文件。"""
    check_chat_id(chat['id'])
    old_name = chat.get('folder')
    if not old_name:
        # 旧版对话还未迁移，只更新标题，首次保存创建正确名称。
        return
    old_path = chat_folder_by_name(old_name)
    new_name = choose_folder_name(proposed_title, chat['id'], current_name=old_name)
    if new_name == old_name:
        return
    new_path = chat_folder_by_name(new_name)
    if not old_path.exists():
        # 目录由外部删除：不偷偷新建或移动其他路径；交给下一次保存处理。
        raise FileNotFoundError(f"当前会话目录不存在：{old_path}")
    if new_path.exists():
        raise FileExistsError(f"目标会话目录已经存在：{new_path}")
    old_path.rename(new_path)
    chat['folder'] = new_name


def save_data():
    """保存当前对话列表到各自 chat.json；不覆盖原总文件和旧 <ID>.json。"""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    for chat in st.session_state.db['conversations']:
        folder = ensure_chat_folder(chat)
        path = folder / CHAT_JSON
        if path.is_symlink():
            raise PermissionError(f"拒绝覆盖符号链接文件：{path}")
        if path.exists():
            existing = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(existing, dict) or existing.get('id') != chat['id']:
                raise ValueError(f"已有 chat.json 属于其他对话，拒绝覆盖：{path}")
        content = json.dumps(chat, ensure_ascii=False, indent=2)
        if path.exists() and path.read_text(encoding='utf-8') == content:
            continue
        temp = folder / f".chat.{uuid4().hex}.tmp"
        try:
            with temp.open('x', encoding='utf-8', newline='\n') as out:
                out.write(content)
            temp.replace(path)  # 同一文件夹内原子替换
        finally:
            temp.unlink(missing_ok=True)


def archive_flat_json():
    """用户主动触发时，把已迁移的旧扁平 JSON 移到备份子目录，不删除。"""
    if not CHAT_DIR.exists():
        return 0
    flat_files = [p for p in sorted(CHAT_DIR.glob('*.json')) if VALID_ID.fullmatch(p.stem)]
    if not flat_files:
        return 0
    new_ids = set()
    for path in CHAT_DIR.glob(f'*/{CHAT_JSON}'):
        item = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(item, dict):
            new_ids.add(item.get('id'))
    backup = CHAT_DIR / '_legacy_json_backup'
    # 先全量检查，避免某个历史聊天没有迁移却被归档。
    for path in flat_files:
        if path.is_symlink() or path.stem not in new_ids:
            raise ValueError(f'尚未确认迁移完成，拒绝归档：{path.name}')
        if (backup / path.name).exists():
            raise FileExistsError(f'备份文件已存在，请先检查：{backup / path.name}')
    backup.mkdir(exist_ok=True)
    for path in flat_files:
        path.rename(backup / path.name)
    return len(flat_files)


def load_data():
    """读取旧总文件、旧扁平 JSON、新文件夹三种结构，以对话 ID 去重。"""
    by_id = {}

    # 旧总文件（只读）。
    if DATA_FILE.exists():
        old = json.loads(DATA_FILE.read_text(encoding='utf-8'))
        if not isinstance(old, dict) or not isinstance(old.get('conversations'), list):
            raise ValueError('旧 conversations.json 格式不正确')
        for item in old['conversations']:
            check_chat_id(item['id'])
            by_id[item['id']] = dict(item)

    # 旧扁平结构：conversations/<UUID>.json（只读）。
    if CHAT_DIR.exists():
        for path in sorted(CHAT_DIR.glob('*.json')):
            if not VALID_ID.fullmatch(path.stem):
                continue
            item = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(item, dict) or item.get('id') != path.stem:
                raise ValueError(f'旧独立文件格式不正确：{path}')
            original = by_id.get(item['id'])
            if original is None or item.get('updated_at', '') >= original.get('updated_at', ''):
                by_id[item['id']] = dict(item)

        # 新结构优先：chat.json 是迁移完成后的权威记录。
        for path in sorted(CHAT_DIR.glob(f'*/{CHAT_JSON}')):
            folder = chat_folder_by_name(path.parent.name)
            item = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(item, dict):
                raise ValueError(f'新对话格式不正确：{path}')
            check_chat_id(item.get('id'))
            item = dict(item)
            item['folder'] = folder.name
            # 不再按 updated_at 与旧扁平文件抢版本，防止已迁移记录回退。
            by_id[item['id']] = item

    if not by_id and OLD_FILE.exists():
        old_messages = json.loads(OLD_FILE.read_text(encoding='utf-8'))
        if isinstance(old_messages, list):
            first = create_chat('原有对话')
            first['messages'] = old_messages
            first['auto_title'] = False
            by_id[first['id']] = first

    if not by_id:
        first = create_chat()
        by_id[first['id']] = first

    return {'conversations': list(by_id.values())}


def current_chat():
    for chat in st.session_state.db['conversations']:
        if chat['id'] == st.session_state.active_id:
            return chat
    raise ValueError('当前对话不存在')


# ==================================
# EDA bridge: history memory + per-chat safe files
# ==================================

MAX_IMPORT_BYTES = 4_000_000  # 单个源码文件最大 4MB
MAX_UPLOAD_FILES = 256
MAX_ARCHIVE_BYTES = 40_000_000
ALLOWED_INPUT_EXT = ALLOWED_EXT


def history_for_agent(chat):
    """Only current conversation, do not send another chat's history."""
    # Exclude the last user message: it is supplied as the current question.
    earlier = chat.get("messages", [])[:-1]
    condensed = []
    for msg in earlier[-12:]:
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        condensed.append({"role": role, "content": str(msg.get("content", ""))[:1300]})
    return json.dumps(condensed, ensure_ascii=False)[-13000:]


def workspace(chat):
    """The entire conversation folder is that chat's workspace."""
    return ensure_chat_folder(chat)


def safe_workspace_subfolder(chat, name):
    """Ensure generated/input target stays within this conversation, no symlink escapes."""
    parent = workspace(chat).resolve()
    base = parent / name
    if base.is_symlink() or not base.resolve().is_relative_to(parent):
        raise PermissionError('工程工作空间含不安全的目录链接')
    return base


def import_rtl_files(chat, uploaded):
    """Import loose source files or .zip EDA projects into conversation inputs/.

    Archive members are validated one by one. This never executes uploaded files.
    """
    if not uploaded:
        return []
    if len(uploaded) > MAX_UPLOAD_FILES:
        raise ValueError(f'一次最多选取 {MAX_UPLOAD_FILES} 个上传文件')
    base = safe_workspace_subfolder(chat, 'inputs')
    pending = {}
    total = 0

    def add_file(name, raw):
        nonlocal total
        name = safe_rel_name(name)
        if len(raw) > MAX_IMPORT_BYTES:
            raise ValueError(f'{name} 超过单文件容量限制')
        if not raw or b'\x00' in raw:
            raise ValueError(f'{name} 不是有效的非空文本')
        raw.decode('utf-8')  # Fail on non-UTF8 rather than silently corrupting RTL.
        total += len(raw)
        if total > MAX_ARCHIVE_BYTES or len(pending) >= MAX_UPLOAD_FILES:
            raise ValueError('单次导入总量超过限制，请分批导入')
        normalized = name.casefold()
        if normalized in pending:
            raise ValueError(f'同一批次出现重复文件名：{name}')
        pending[normalized] = (name, raw)

    for f in uploaded:
        content = f.getvalue()
        if f.name.lower().endswith('.zip'):
            if len(content) > MAX_ARCHIVE_BYTES:
                raise ValueError('ZIP 压缩包体积过大')
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                entries = zf.infolist()
                if len(entries) > MAX_UPLOAD_FILES * 3:
                    raise ValueError('ZIP 条目数量过多')
                for info in entries:
                    if info.is_dir():
                        continue
                    # Reject Unix symbolic links stored in zip.
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError(f'ZIP 含符号链接：{info.filename}')
                    if info.file_size > MAX_IMPORT_BYTES:
                        raise ValueError(f'ZIP 条目太大：{info.filename}')
                    if info.filename.startswith('__MACOSX/') or '/.' in info.filename:
                        continue
                    try:
                        path = safe_rel_name(info.filename)
                    except ValueError:
                        # Disallowed extensions may be ignored, unsafe paths must NOT.
                        parts = info.filename.replace('\\', '/').split('/')
                        if any(x in ('', '.', '..') for x in parts) or ':' in info.filename or info.filename.startswith(('/', '\\')):
                            raise ValueError(f'ZIP 存在不安全路径：{info.filename}')
                        continue
                    add_file(path, zf.read(info))
        else:
            add_file(f.name, content)

    if not pending:
        raise ValueError('上传内容中没有支持的 EDA 文本文件')
    # Preflight all paths; there is no overwrite/escape, even after symlink resolution.
    targets = []
    for name, raw in pending.values():
        target = base.joinpath(*name.split('/'))
        if not target.resolve().is_relative_to(base.resolve()):
            raise PermissionError(f'目标超出 inputs：{name}')
        current = base
        for component in name.split('/')[:-1]:
            current = current / component
            if current.is_symlink():
                raise PermissionError(f'包含目录链接：{name}')
        if target.exists() or target.is_symlink():
            raise FileExistsError(f'文件已存在：{target}（不会覆盖）')
        targets.append((target, raw))
    created = []
    try:
        for target, raw in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.resolve().is_relative_to(base.resolve()):
                raise PermissionError(f'路径越界：{target.name}')
            with target.open('xb') as stream:
                created.append(target)
                stream.write(raw)
    except Exception:
        for t in created:
            t.unlink(missing_ok=True)
        raise
    return [t.relative_to(workspace(chat)).as_posix() for t, _ in targets]


def check_drafts_for_saving(chat, drafts):
    """Check all relative paths before writing, without global mutable OUTPUT_DIR."""
    base = safe_workspace_subfolder(chat, 'generated')
    targets, names = [], set()
    for d in drafts:
        name = safe_rel_name(d['name'])
        if name.casefold() in names:
            raise ValueError(f'重复输出路径：{name}')
        names.add(name.casefold())
        if not isinstance(d['code'], str) or len(d['code'].encode('utf-8')) > MAX_DRAFT_BYTES:
            raise ValueError(f'{name} 源码内容不合法或过大')
        target = base / name
        if not target.resolve().is_relative_to(base.resolve()):
            raise PermissionError(f'生成目录跳转越界：{name}')
        for folder in target.parents:
            if folder == base.parent:
                break
            if folder.is_symlink():
                raise PermissionError(f'生成目标含目录链接：{name}')
        if target.exists():
            raise FileExistsError(f'目标文件已存在：{name}，请更名，不会覆盖')
        targets.append(target)
    return targets


def save_reviewed_drafts(chat, drafts):
    targets = check_drafts_for_saving(chat, drafts)
    created = []
    try:
        for d, target in zip(drafts, targets):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.resolve().is_relative_to(safe_workspace_subfolder(chat, 'generated').resolve()):
                raise PermissionError('生成文件夹在保存时越界')
            with target.open('x', encoding='utf-8', newline='\n') as f:
                created.append(target)
                f.write(d['code'])
    except Exception:
        for t in created:
            t.unlink(missing_ok=True)
        raise
    root = workspace(chat)
    return [t.relative_to(root).as_posix() for t in targets]


def run_agent_for_chat(chat):
    current = chat['messages'][-1]
    if current.get('role') != 'user':
        raise ValueError('最近一条不是用户消息，无法执行 Agent')
    return run_task(
        question=str(current['content']),
        history_context=history_for_agent(chat),
        workspace=workspace(chat),
    )


# ==================================
# 2. 初始化 Streamlit 状态（旧版保留）
# ==================================

st.set_page_config(page_title="EDA 智能助手 v8", page_icon="🤖", layout="wide")

if "db" not in st.session_state:
    try:
        st.session_state.db = load_data()
    except (json.JSONDecodeError, OSError, ValueError, KeyError, TypeError) as e:
        st.error(f"读取聊天记录失败，请先备份数据文件：{e}")
        st.stop()

if not st.session_state.db["conversations"]:
    st.session_state.db["conversations"].append(create_chat())

if "active_id" not in st.session_state:
    st.session_state.active_id = st.session_state.db["conversations"][0]["id"]

if "edit_index" not in st.session_state:
    st.session_state.edit_index = None

if "pending_reply" not in st.session_state:
    st.session_state.pending_reply = False


# ==================================
# 3. 侧边栏：新建及切换对话（旧版保留）
# ==================================

st.sidebar.title("EDA 智能助手")

# 首次迁移需要显式点击；旧版独立 JSON 与单文件备份都不会删除。
if st.sidebar.button("迁移历史对话到独立文件夹", use_container_width=True):
    try:
        save_data()
        st.sidebar.success("迁移完成：每段对话一个文件夹。旧 JSON 已保留。")
    except Exception as exc:
        st.sidebar.error(f"迁移失败，旧 JSON 没有删除：{exc}")

# 旧 JSON 归档按钮暂时不展示：历史文件不会被移动或删除。

if st.sidebar.button("＋ 新建对话", use_container_width=True):
    new_chat = create_chat()
    st.session_state.db["conversations"].append(new_chat)
    st.session_state.active_id = new_chat["id"]
    st.session_state.edit_index = None
    st.session_state.pending_reply = False
    save_data()
    st.rerun()

st.sidebar.subheader("历史对话")

sorted_chats = sorted(
    st.session_state.db["conversations"],
    key=lambda x: x["updated_at"],
    reverse=True,
)

for chat in sorted_chats:
    is_active = chat["id"] == st.session_state.active_id
    if st.sidebar.button(
        "💬 " + chat["title"],
        key="chat_" + chat["id"],
        type="primary" if is_active else "secondary",
        use_container_width=True,
    ):
        st.session_state.active_id = chat["id"]
        st.session_state.edit_index = None
        st.session_state.pending_reply = False
        st.rerun()

chat = current_chat()


# ==================================
# 4. 侧边栏：修改对话名称（旧版保留）
# ==================================

st.sidebar.divider()
st.sidebar.subheader("重命名当前对话")

with st.sidebar.form(key="rename_" + chat["id"]):
    new_title = st.text_input("对话名称", value=chat["title"])
    rename_submit = st.form_submit_button("保存名称")

if rename_submit and new_title.strip():
    try:
        rename_chat_folder(chat, new_title.strip())
        chat["title"] = new_title.strip()
        chat["auto_title"] = False
        chat["updated_at"] = now()
        save_data()
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f"重命名失败，原会话数据仍保留：{exc}")

st.sidebar.divider()
st.sidebar.caption("当前对话工作空间：")
if chat.get("folder"):
    st.sidebar.code(str(CHAT_DIR / chat["folder"]), language=None)
else:
    st.sidebar.caption("尚未迁移；点击上方迁移按钮可创建工作空间。")


# ==================================
# 4a. 当前对话内导入已有工程文件
# ==================================

st.sidebar.divider()
st.sidebar.subheader('导入工程文件')
st.sidebar.caption('可以选择多个 RTL/脚本，或上传整个工程 ZIP（保留子目录）。文件复制到本聊天 inputs/，源位置不修改；模型按需读取。')
with st.sidebar.form(key='upload_rtl_' + chat['id']):
    uploaded = st.file_uploader(
        '选择 EDA 文本文件或 ZIP 工程包',
        type=['v', 'sv', 'vh', 'svh', 'f', 'sdc', 'tcl', 'txt', 'py', 'sh', 'mk', 'md', 'json', 'yml', 'yaml', 'cfg', 'ini', 'xdc', 'zip'],
        accept_multiple_files=True,
        key='files_' + chat['id'],
    )
    import_click = st.form_submit_button('导入当前对话工作空间')
if import_click:
    try:
        files = import_rtl_files(chat, uploaded)
        st.sidebar.success(f'导入成功 {len(files)} 份文件。' + (' 文件举例：' + ', '.join(files[:8]) if files else ''))
    except Exception as exc:
        st.sidebar.error(f'导入失败：{exc}')

# ==================================
# 5. 主聊天页面（旧版保留）
# ==================================

st.title(chat["title"])
st.caption("LangGraph + DeepSeek | v8.2 固定工程目录 + VCS 独立运行记录 | 保留 v7 审批")

# ==================================
# v8 远程 EDA：独立显式操作，绝不自动运行模型编写的 .sh/.tcl
# ==================================

with st.expander('🔗 Linux 工程目录与 VCS 执行（v8.2）', expanded=False):
    st.caption('在指定的 Linux 根目录下建立可读工程名，工程路径固定；上传同步当前批准的源码，每次 VCS 在 runs/vcs_001、vcs_002 等独立目录留存源码快照与日志。不会改动旧 adder 工程。')
    st.caption('SSH 主机指纹使用 Windows 已确认的 ~/.ssh/known_hosts；密码仅用于当前连接，不写入 chat.json。IP 可能随 DHCP 更新。')
    if chat.get('pending_drafts'):
        st.warning('本对话还有待审批草稿。远程上传只能使用先前已经保存的文件，不会上传这些未审批草稿。')
    try:
        preview = file_preview(workspace(chat))
        st.write(f"本地已保存工程：{preview['file_count']} 个文件；VCS 源文件 {len(preview['sources'])} 个")
        if preview['excluded']:
            st.info('检测到被新生成版本替代的输入源码（不会参加自动 VCS 编译）：' + '、'.join(preview['excluded'][:12]))
        if st.checkbox('显示 VCS 自动收集的源文件', value=False, key='v8_preview_' + chat['id']):
            st.code('\n'.join(preview['sources']), language='text')
        default_tb = preview['testbenches'][0] if preview['testbenches'] else ''
        if preview.get('vcs_preview_error'):
            st.info('VCS 暂不可用：' + preview['vcs_preview_error'])
    except (OSError, ValueError, RemoteError) as exc:
        preview = None
        default_tb = ''
        st.info(f'尚未准备好可仿真的工程：{exc}')

    with st.form('v8_ssh_form_' + chat['id']):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            ssh_host = st.text_input('虚拟机 IP / 主机名', value=os.getenv('EDA_SSH_HOST', '192.168.81.128'), key='v8_host')
        with c2:
            ssh_user = st.text_input('Linux 用户', value=os.getenv('EDA_SSH_USER', 'IC'), key='v8_user')
        with c3:
            ssh_port = st.number_input('SSH 端口', min_value=1, max_value=65535, value=22, step=1, key='v8_port')
        ssh_password = st.text_input('SSH 密码（可留空以使用 SSH Agent/密钥）', type='password', key='v8_password')
        remote_base = st.text_input(
            'Linux 上传根目录（可以自己指定）',
            value=chat.get('remote_project_config', {}).get('remote_base', os.getenv('EDA_REMOTE_BASE', '~/Desktop/EDA_Projects')),
            key='v8_remote_base_' + chat['id'],
            help='例如：~/Desktop/EDA_Projects 或 /home/IC/Desktop/EDA_Projects；仅支持当前 SSH 用户家目录下的安全路径。',
        )
        project_name = st.text_input(
            'Linux 工程名称（固定，支持中文、英文、数字、下划线、短横线）',
            value=chat.get('remote_project_config', {}).get('project_name', 'Project_' + chat['id'][:6]),
            key='v82_project_name_' + chat['id'],
            help='例如 UART_RX、Counter、计数器。目标工程目录必须为空闲或之前由当前聊天创建；不会接管已有同名工程。',
        )
        st.caption('实际工程路径 = 根目录 / 工程名称；运行目录 = 工程路径 / runs / vcs_001、vcs_002…；上传版本 = runs/upload_001…')
        tb_top = st.text_input('VCS Testbench 顶层模块名（如 tb_counter）', value=default_tb, key='v8_tb_' + chat['id'])
        st.caption('v8 首版：自动编译所有已保存的 .v/.sv，并自动加入包含头文件的目录；暂不解释 .f 文件，也不执行上传的 .sh/.tcl。')
        autofix_rounds = st.number_input('自动纠错最多轮数', min_value=1, max_value=5, value=3, step=1,
                                         key='v8_autofix_rounds_' + chat['id'])
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            check_connection = st.form_submit_button('① 测试 SSH', use_container_width=True)
        with b2:
            upload_only = st.form_submit_button('② 上传工程版本', use_container_width=True, disabled=(preview is None))
        with b3:
            vcs_run = st.form_submit_button('③ VCS 编译仿真', use_container_width=True, disabled=(preview is None or not bool(preview['sources'])))
        with b4:
            autofix_run = st.form_submit_button('④ 自动纠错闭环', use_container_width=True,
                                                disabled=(preview is None or not bool(preview['sources'])))

    ssh_action = check_connection or upload_only or vcs_run or autofix_run
    if ssh_action and not (ssh_password or '').strip():
        st.caption('未填写密码：将尝试 SSH Agent / 默认密钥认证；若失败，请填写密码后重试。')
    if ssh_action:
        if st.session_state.pending_reply:
            st.error('Agent 正在生成回答，请等待当前任务完成。')
        else:
            cfg = SSHSettings(host=ssh_host.strip(), user=ssh_user.strip(), port=int(ssh_port), password=ssh_password)
            with st.spinner('正在连接 Linux 虚拟机；VCS 首次编译可能耗时数分钟...'):
                try:
                    if autofix_run:
                        from eda_autofix import run_autofix
                        with st.status('自动纠错闭环运行中…', expanded=True) as box:
                            def _log(msg):
                                box.write(msg)

                            res = run_autofix(
                                cfg, workspace(chat), chat['id'], tb_top.strip(),
                                remote_base.strip(), project_name.strip(),
                                max_iterations=int(autofix_rounds), log=_log,
                            )
                            box.update(label=f"闭环结束：{res['final_status']}（{len(res['iterations'])} 轮）",
                                       state='complete' if res['ok'] else 'error')
                        st.session_state['v8_autofix_' + chat['id']] = res
                        # 闭环各轮也写入持久化历史，历史页才能像普通运行一样查看文件/哈希/日志
                        for item in res.get('iterations') or []:
                            chat.setdefault('remote_history', []).append({
                                'run_id': item.get('run_id', ''),
                                'mode': 'autofix',
                                'status': item.get('status', ''),
                                'when': now(),
                                'run_label': item.get('run_label', ''),
                                'remote_directory': item.get('remote_directory', ''),
                                'local_directory': item.get('local_directory', ''),
                                'sources': item.get('sources') or [],
                                'compile_exit_code': item.get('compile_exit_code'),
                                'sim_exit_code': item.get('sim_exit_code'),
                                'coverage': item.get('coverage') or {},
                            })
                        chat['updated_at'] = now()
                        save_data()
                    elif check_connection:
                        check = connection_probe(cfg)
                        st.success('SSH 连接和安全的工具路径探测成功。')
                        st.code(check['stdout'], language='text')
                    else:
                        mode = 'vcs' if vcs_run else 'upload'
                        if chat.get('pending_drafts'):
                            st.info('提示：待审阅草稿没有被上传，本轮仅使用已有已保存文件。')
                        r = remote_job(cfg, workspace(chat), chat['id'], mode=mode, tb_top=tb_top.strip(),
                                       remote_base=remote_base.strip(), project_name=project_name.strip())
                        # Record metadata only, never raw logs, full source code or credentials.
                        meta = {k: r.get(k) for k in ('run_id', 'mode', 'status', 'when', 'file_count',
                                                      'project_directory', 'run_label', 'source_snapshot',
                                                      'sync', 'sync_error', 'remote_directory', 'local_directory',
                                                      'compile_exit_code', 'sim_exit_code', 'sources',
                                                      'excluded_sources', 'coverage', 'coverage_error') if k in r}
                        chat['remote_project_config'] = {'remote_base': remote_base.strip(), 'project_name': project_name.strip()}
                        chat.setdefault('remote_history', []).append(meta)
                        chat['remote_history'] = chat['remote_history'][-500:]
                        chat['updated_at'] = now()
                        save_data()
                        st.success('工程上传完成。' if mode == 'upload' else f"VCS 运行结束，判定：{r['status']}")
                        cov = r.get('coverage') or {}
                        if mode == 'vcs' and cov.get('score') is not None:
                            def _pct(v):
                                return '--' if v is None else f'{v:.2f}%'
                            st.info(
                                '覆盖率（urg，代码覆盖率）：'
                                f"总分 {_pct(cov.get('score'))} · "
                                f"行 {_pct(cov.get('line'))} · "
                                f"分支 {_pct(cov.get('branch'))} · "
                                f"翻转 {_pct(cov.get('toggle'))}"
                            )
                        elif mode == 'vcs' and r.get('coverage_error'):
                            st.caption('覆盖率报告未生成：' + str(r['coverage_error']))
                        st.caption('固定工程目录：')
                        st.code(r['project_directory'], language='text')
                        st.caption(f"本次运行：{r['run_label']}；独立快照与日志：")
                        st.code(r['remote_directory'], language='text')
                        if r.get('sync_error'):
                            st.warning('当前版本同步有警告（本次运行快照仍已留存）：' + r['sync_error'])
                        if mode == 'vcs':
                            st.caption('注意：无显式 PASS 标记时，退出码为 0 也只记为 finished_unverified；不是宣称验证通过。')
                except Exception as exc:
                    st.error(f'远程操作失败：{type(exc).__name__}: {exc}')

    remote_history = chat.get('remote_history') or []
    if remote_history:
        last = remote_history[-1]
        st.markdown(f"**最近一次远程操作：** {last.get('status')} · `{last.get('run_label', '?')}`")
        st.caption('Linux 工程目录：' + str(last.get('project_directory', '未知')))
        st.caption('独立运行目录：' + str(last.get('remote_directory', '未知')))

        # 覆盖率随历史记录持久显示，不依赖本轮按钮状态（否则一勾选日志就消失）
        last_cov = last.get('coverage') or {}
        if last.get('mode') == 'vcs':
            if last_cov.get('score') is not None:
                def _fmt_pct(v):
                    return '--' if v is None else f'{v:.2f}%'
                st.caption(
                    '覆盖率（urg，代码覆盖率）：'
                    f"总分 {_fmt_pct(last_cov.get('score'))} · "
                    f"行 {_fmt_pct(last_cov.get('line'))} · "
                    f"分支 {_fmt_pct(last_cov.get('branch'))} · "
                    f"翻转 {_fmt_pct(last_cov.get('toggle'))}"
                )
            elif last.get('coverage_error'):
                st.caption('覆盖率报告未生成：' + str(last['coverage_error']))

        rid = str(last.get('run_id', ''))
        if re.fullmatch(r'[0-9a-f]{32}', rid):
            run_dir = safe_workspace_subfolder(chat, 'remote_runs') / rid
            root = workspace(chat).resolve()

            def _log_viewer(chat_id: str, run_id: str, base: str, safe_root) -> None:
                base_path = Path(base)
                for log_name in ('vcs_compile.log', 'vcs_sim.log'):
                    local_log = base_path / log_name
                    if (local_log.is_symlink() or not local_log.is_file()
                            or not local_log.resolve().is_relative_to(safe_root)):
                        continue
                    if st.checkbox(f'显示 {log_name}（末尾 14000 字符）', value=False,
                                   key=f'v8_show_log_{chat_id}_{run_id}_{log_name}'):
                        log_text = local_log.read_text(encoding='utf-8', errors='replace')
                        st.code(log_text[-14000:], language='text')
                        st.download_button(f'下载 {log_name}', data=log_text,
                                           file_name=f'{run_id[:8]}_{log_name}', mime='text/plain',
                                           key=f'v8_download_{chat_id}_{run_id}_{log_name}')

            # 用 fragment 把日志查看限制在局部重跑，减少整页 DOM 重排（缓解 removeChild）
            try:
                st.fragment(_log_viewer)(chat['id'], rid, str(run_dir), root)
            except Exception:  # 旧版 Streamlit 没有 fragment
                _log_viewer(chat['id'], rid, str(run_dir), root)

    with st.expander('📊 结果分析（本对话）', expanded=False):
        import pandas as pd

        from eda_analysis import build_markdown, collect_run_metrics, summarize

        metric_rows = collect_run_metrics(chat)
        if not metric_rows:
            st.caption('还没有 VCS 运行记录。先生成工程并点 ③。')
        else:
            s = summarize(metric_rows)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric('累计运行', s['runs'])
            m2.metric('通过率', f"{s['pass_rate']:.0%}")
            if s.get('latest_coverage') is not None:
                delta = f"{s['coverage_delta']:+.2f} pp" if s.get('coverage_delta') is not None else None
                m3.metric('最新覆盖率', f"{s['latest_coverage']:.2f}%", delta=delta)
            else:
                m3.metric('最新覆盖率', '—')
            m4.metric('检查点', s.get('latest_checks') or '—',
                      delta=(f"{s['checks_delta']:+d}" if s.get('checks_delta') else None))

            show = pd.DataFrame(metric_rows)
            for hidden in ('失败模式', '_scenarios', '_seeds'):
                if hidden in show.columns:
                    show = show.drop(columns=[hidden])
            st.dataframe(show.tail(15), use_container_width=True, hide_index=True)

            detail = []
            if s.get('latest_passed') is not None:
                detail.append(f"通过 {s['latest_passed']}/{s.get('latest_checks')}")
            if s.get('latest_scenarios'):
                detail.append(f"场景 {s['latest_scenarios']} 类")
            if s.get('latest_seeds'):
                detail.append(f"随机种子 {s['latest_seeds']} 个")
            if s.get('latest_bins'):
                detail.append(f"功能覆盖 {s['latest_bins']}")
            if s.get('latest_ended'):
                detail.append(f"结束标记 {s['latest_ended']}")
            if detail:
                st.caption('最新一轮：' + ' · '.join(detail))
            if s.get('scenario_detail') or s.get('seed_detail'):
                with st.expander('最新一轮的场景与种子', expanded=False):
                    if s.get('scenario_detail'):
                        st.write('场景：' + '、'.join(s['scenario_detail']))
                    if s.get('seed_detail'):
                        st.write('种子：' + '、'.join(str(x) for x in s['seed_detail']))

            if s.get('coverage_series'):
                st.caption('覆盖率趋势（仅统计已接入 urg 的运行）')
                st.line_chart(pd.DataFrame(s['coverage_series']).set_index('运行'), height=220)
            if s.get('checks_series'):
                st.caption('检查点数量趋势')
                st.bar_chart(pd.DataFrame(s['checks_series']).set_index('运行'), height=200)

            if s.get('failed_runs'):
                st.warning('存在失败轮次：')
                for r in s['failed_runs']:
                    st.caption(f"· {r['运行']}：{r['失败模式'] or '（日志里没有 exp/got 明细）'}")

            md = build_markdown(metric_rows, s, title=f"结果分析 · {chat.get('title', '对话')}")
            st.download_button(
                '⬇️ 导出分析摘要（Markdown）',
                data=md.encode('utf-8'),
                file_name=f"分析摘要_{chat['id'][:6]}.md",
                mime='text/markdown',
                key='v8_export_analysis_' + chat['id'],
                help='包含汇总指标、逐轮指标、覆盖率趋势与失败轮次，可直接粘进报告。',
            )

    with st.expander('📜 运行历史（逐轮查看）', expanded=False):
        from eda_analysis import load_run_detail

        hist = [h for h in chat.get('remote_history', []) if h.get('mode') in ('vcs', 'autofix')]
        if not hist:
            st.caption('还没有 VCS 运行记录。')
        else:
            labels = [h.get('run_label') for h in hist][::-1]
            pick = st.selectbox('选择轮次（最新在前）', labels, key='v8_hist_' + chat['id'])
            entry = next(h for h in hist if h.get('run_label') == pick)
            det = load_run_detail(entry, workspace(chat))
            summary = det.get('summary') or {}

            h1, h2, h3, h4 = st.columns(4)
            h1.metric('状态', summary.get('status') or entry.get('status') or '?')
            h2.metric('编译/仿真码',
                      f"{summary.get('compile_exit_code')}/{summary.get('sim_exit_code')}")
            cov = (summary.get('coverage') or {}).get('score')
            h3.metric('覆盖率', f'{cov:.2f}%' if cov is not None else '—')
            h4.metric('源文件数', len(summary.get('sources') or []))

            if summary.get('sources'):
                st.caption('编译源文件：' + '、'.join(summary['sources']))
            if summary.get('compile_config_used') is not None:
                mode_txt = 'compile_cfg.json' if summary['compile_config_used'] else '自动扫描'
                defs = summary.get('defines') or []
                st.caption('编译配置：' + mode_txt
                           + (f" · defines: {', '.join(defs)}" if defs else ''))

            files = (det.get('manifest') or {}).get('files_sha256') or {}
            if files:
                st.caption(f'源码快照 SHA-256（{len(files)} 个文件）：')
                st.dataframe([{'文件': k, 'SHA-256': v} for k, v in files.items()],
                             use_container_width=True, hide_index=True)
            else:
                st.caption('该轮没有本地快照清单（旧版本运行或未回填）。')

            if det.get('error_excerpt'):
                st.caption('错误摘要：')
                st.code(det['error_excerpt'], language='text')

            dl1, dl2 = st.columns(2)
            base = Path(entry.get('local_directory') or '')
            for col, name, flag in ((dl1, 'vcs_compile.log', det.get('has_compile_log')),
                                    (dl2, 'vcs_sim.log', det.get('has_sim_log'))):
                with col:
                    f = base / name
                    if flag and f.is_file():
                        st.download_button(
                            f'下载 {name}', data=f.read_bytes(),
                            file_name=f'{pick}_{name}', mime='text/plain',
                            key=f'v8_hist_dl_{chat["id"]}_{pick}_{name}',
                        )

    auto_res = st.session_state.get('v8_autofix_' + chat['id'])
    if auto_res:
        st.markdown('---')
        st.subheader('自动纠错闭环结果')
        st.caption(f"影子目录（未改动已批准文件）：{auto_res.get('shadow_dir')}")
        rows = [{
            '轮次': it['index'],
            '状态': it['status'],
            '错误类型': it['error_type'] or '-',
            '运行标签': it['run_label'],
            '编译退出码': it['compile_exit_code'],
            '仿真退出码': it['sim_exit_code'],
            '改动文件': ', '.join(it['changed_files']) or '-',
        } for it in auto_res['iterations']]
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        if auto_res.get('error'):
            st.warning(auto_res['error'])
        if auto_res['ok']:
            st.success('闭环成功：最后一轮判定 passed_by_marker')
        else:
            st.error(f"未收敛：最后状态 {auto_res['final_status']}")

        for d in auto_res.get('diffs') or []:
            with st.expander(f"补丁：{d['path']}"):
                st.code(d['diff'], language='diff')

        if auto_res.get('diffs'):
            if st.button('采纳这套修改并写入 generated/（覆盖同名文件）', key='v8_adopt_' + chat['id']):
                from eda_autofix import adopt_result
                written = adopt_result(workspace(chat), auto_res)
                st.session_state.pop('v8_autofix_' + chat['id'], None)
                st.success('已写入：' + (', '.join(written) if written else '无变化'))
                st.rerun()
        if st.button('清除本次闭环结果', key='v8_clear_autofix_' + chat['id']):
            st.session_state.pop('v8_autofix_' + chat['id'], None)
            st.rerun()


for i, message in enumerate(chat["messages"]):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] == "user":
            if st.button("✏️ 编辑", key=f"edit_{chat['id']}_{i}"):
                st.session_state.edit_index = i
                st.rerun()

            if st.session_state.edit_index == i:
                with st.form(key=f"edit_form_{chat['id']}_{i}"):
                    new_text = st.text_area("修改消息", value=message["content"])
                    save_edit = st.form_submit_button("保存并重新生成")
                    cancel_edit = st.form_submit_button("取消")

                if save_edit and new_text.strip():
                    chat["messages"] = chat["messages"][:i] + [
                        {"role": "user", "content": new_text.strip()}
                    ]
                    chat["updated_at"] = now()
                    st.session_state.edit_index = None
                    st.session_state.pending_reply = True
                    chat["pending_drafts"] = []
                    chat.pop("draft_batch_id", None)
                    save_data()
                    st.rerun()

                if cancel_edit:
                    st.session_state.edit_index = None
                    st.rerun()


# ==================================
# 5a. 当前聊天待审阅草稿（保存在本对话 chat.json 中）
# ==================================

pending_drafts = chat.get('pending_drafts') or []
if pending_drafts:
    st.divider()
    st.subheader(f'待审阅的完整任务草稿（{len(pending_drafts)} 份，尚未写入文件）')
    st.caption('包含 RTL、Testbench、脚本和 filelist 等文本文件；所有草稿统一审批，不覆盖已有文件，也不执行脚本。')
    for index, draft in enumerate(pending_drafts, 1):
        st.markdown(f'**草稿 {index}/{len(pending_drafts)}：{draft["name"]}**')
        if draft.get('purpose'):
            st.caption('用途：' + str(draft['purpose']))
        if draft.get('source'):
            st.caption(f'根据文件 {draft["source"]} 修改，原文件保持不变')
            changes = ''.join(difflib.unified_diff(
                draft.get('original', '').splitlines(True),
                draft['code'].splitlines(True),
                fromfile=draft['source'], tofile=draft['name'],
            ))
            if changes:
                with st.expander('查看修改差异 (diff)', expanded=False):
                    st.code(changes[:50000], language='diff')
        elif draft.get('references'):
            st.caption('用于参考的原始 RTL：' + ', '.join(draft['references']))
        with st.expander('查看完整代码', expanded=(len(pending_drafts) == 1)):
            st.code(draft['code'][:50000], language=('verilog' if str(draft['name']).endswith(('.v','.sv','.vh','.svh')) else 'text'))
            if len(draft['code']) > 50000:
                st.caption(f'预览只展示前 50000 字符，完整代码共 {len(draft["code"])} 字符，请使用下面的下载按钮审阅。')
            st.download_button('下载这份草稿供详细审阅', data=draft['code'],
                               file_name=Path(draft['name']).name, mime='text/plain',
                               key=f'download_{chat["id"]}_{chat.get("draft_batch_id", "legacy")}_{index}')

    with st.form(key='approve_drafts_' + chat['id']):
        names = [
            st.text_input(f'草稿 {i} 的保存相对路径', value=d['name'], key=f'draft_name_{chat["id"]}_{chat.get("draft_batch_id", "legacy")}_{i}')
            for i, d in enumerate(pending_drafts, 1)
        ]
        approve = st.form_submit_button('确认保存本任务全部文件')
    if approve:
        reviewed = [{**d, 'name': n.strip()} for d, n in zip(pending_drafts, names)]
        try:
            saved = save_reviewed_drafts(chat, reviewed)
            chat['pending_drafts'] = []
            chat.pop('draft_batch_id', None)
            chat['updated_at'] = now()
            chat['messages'].append({
                'role': 'assistant',
                'content': '已在当前聊天工作空间中一次性保存以下文件（原文件未覆盖）：\n' +
                           '\n'.join(f'- `{f}`' for f in saved) +
                           '\n\n尚未执行脚本、VCS 仿真或 DC 综合。'
            })
            save_data()
            st.rerun()
        except Exception as exc:
            st.error(f'保存失败：{exc}；请检查文件名，不会覆盖已有文件。')
    if st.button('取消这些草稿', key='cancel_drafts_' + chat['id']):
        chat['pending_drafts'] = []
        chat.pop('draft_batch_id', None)
        chat['updated_at'] = now()
        save_data()
        st.rerun()

# ==================================
# 6. 用户输入（旧版保留）
# ==================================

user_input = st.chat_input(
    "描述完整任务，例如：设计 UART 接收、顶层、testbench 与 filelist",
    disabled=(
        st.session_state.pending_reply
        or bool(chat.get("pending_drafts"))
        or st.session_state.edit_index is not None
    ),
)

if user_input:
    chat["messages"].append({"role": "user", "content": user_input})

    if chat["auto_title"]:
        title = user_input.replace("\n", " ").strip()
        proposed_title = title[:20] + "..." if len(title) > 20 else title
        try:
            rename_chat_folder(chat, proposed_title)
        except (OSError, PermissionError, ValueError) as exc:
            st.warning(f"首次对话目录改名失败，保留原目录：{exc}")
        chat["title"] = proposed_title
        chat["auto_title"] = False

    chat["updated_at"] = now()
    save_data()
    st.session_state.pending_reply = True
    st.rerun()


# ==================================
# 7. 调用 DeepSeek（旧版保留）
# ==================================

if st.session_state.pending_reply:
    with st.chat_message("assistant"):
        with st.spinner("DeepSeek 正在规划并逐个生成全部工程文件，复杂任务可能需要较长时间..."):
            try:
                agent_result = run_agent_for_chat(chat)
                answer = agent_result['answer']
                drafts = agent_result['drafts']
                if drafts:
                    answer += '\n\n所有生成文件已汇总到下方审阅区；确认后才会统一保存。'
                    chat['pending_drafts'] = drafts
                    chat['draft_batch_id'] = uuid4().hex
                chat['messages'].append({"role": "assistant", "content": answer})
                chat["updated_at"] = now()
                save_data()
                st.session_state.pending_reply = False
                st.rerun()

            except Exception as e:
                st.session_state.pending_reply = False
                st.error(f"调用失败：{e}")

if (
    chat["messages"]
    and chat["messages"][-1]["role"] == "user"
    and not st.session_state.pending_reply
):
    if st.button("重新获取回答"):
        st.session_state.pending_reply = True
        st.rerun()
