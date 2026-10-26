/////////////////////////////////////////////////////////////
// Created by: Synopsys DC Expert(TM) in wire load mode
// Version   : K-2015.06
// Date      : Sat Oct 24 23:36:18 2026
/////////////////////////////////////////////////////////////


module counter_8bit_DW01_inc_0 ( A, SUM );
  input [7:0] A;
  output [7:0] SUM;

  wire   [7:2] carry;

  ADDHX1 U1_1_6 ( .A(A[6]), .B(carry[6]), .CO(carry[7]), .S(SUM[6]) );
  ADDHX1 U1_1_5 ( .A(A[5]), .B(carry[5]), .CO(carry[6]), .S(SUM[5]) );
  ADDHX1 U1_1_4 ( .A(A[4]), .B(carry[4]), .CO(carry[5]), .S(SUM[4]) );
  ADDHX1 U1_1_3 ( .A(A[3]), .B(carry[3]), .CO(carry[4]), .S(SUM[3]) );
  ADDHX1 U1_1_2 ( .A(A[2]), .B(carry[2]), .CO(carry[3]), .S(SUM[2]) );
  ADDHX1 U1_1_1 ( .A(A[1]), .B(A[0]), .CO(carry[2]), .S(SUM[1]) );
  XOR2X1 U1 ( .A(carry[7]), .B(A[7]), .Y(SUM[7]) );
  CLKINVX1 U2 ( .A(A[0]), .Y(SUM[0]) );
endmodule


module counter_8bit ( clk, rst_n, en, count );
  output [7:0] count;
  input clk, rst_n, en;
  wire   N2, N3, N4, N5, N6, N7, N8, N9, n2, n3, n4, n5, n6, n7, n8, n9, n10;

  counter_8bit_DW01_inc_0 add_20 ( .A(count), .SUM({N9, N8, N7, N6, N5, N4, N3, 
        N2}) );
  DFFRQX2 count_reg_7_ ( .D(n2), .CK(clk), .RN(rst_n), .Q(count[7]) );
  DFFRQX2 count_reg_0_ ( .D(n9), .CK(clk), .RN(rst_n), .Q(count[0]) );
  DFFRQX2 count_reg_1_ ( .D(n8), .CK(clk), .RN(rst_n), .Q(count[1]) );
  DFFRQX2 count_reg_2_ ( .D(n7), .CK(clk), .RN(rst_n), .Q(count[2]) );
  DFFRQX2 count_reg_3_ ( .D(n6), .CK(clk), .RN(rst_n), .Q(count[3]) );
  DFFRQX2 count_reg_4_ ( .D(n5), .CK(clk), .RN(rst_n), .Q(count[4]) );
  DFFRQX2 count_reg_5_ ( .D(n4), .CK(clk), .RN(rst_n), .Q(count[5]) );
  DFFRQX2 count_reg_6_ ( .D(n3), .CK(clk), .RN(rst_n), .Q(count[6]) );
  INVX2 U12 ( .A(en), .Y(n10) );
  AO22X2 U13 ( .A0(count[6]), .A1(n10), .B0(N8), .B1(en), .Y(n3) );
  AO22X2 U14 ( .A0(count[5]), .A1(n10), .B0(N7), .B1(en), .Y(n4) );
  AO22X2 U15 ( .A0(count[4]), .A1(n10), .B0(N6), .B1(en), .Y(n5) );
  AO22X2 U16 ( .A0(count[3]), .A1(n10), .B0(N5), .B1(en), .Y(n6) );
  AO22X2 U17 ( .A0(count[2]), .A1(n10), .B0(N4), .B1(en), .Y(n7) );
  AO22X2 U18 ( .A0(count[1]), .A1(n10), .B0(N3), .B1(en), .Y(n8) );
  AO22X2 U19 ( .A0(count[0]), .A1(n10), .B0(N2), .B1(en), .Y(n9) );
  AO22X2 U20 ( .A0(count[7]), .A1(n10), .B0(en), .B1(N9), .Y(n2) );
endmodule

