// Small ALU for scratch ops (X--, compares later) and immediate expand.
module kraken_alu (
  input  kraken_pkg::alu_op_e op,
  input  kraken_pkg::data_t   a,
  input  kraken_pkg::data_t   b,
  output kraken_pkg::data_t   y,
  output logic                z   // result == 0
);
  always_comb begin
    unique case (op)
      kraken_pkg::ALU_PASS_A: y = a;
      kraken_pkg::ALU_DEC:    y = a - kraken_pkg::data_t'(1);
      kraken_pkg::ALU_ADD:    y = a + b;
      kraken_pkg::ALU_SUB:    y = a - b;
      default:    y = a;
    endcase
    z = (y == '0);
  end
endmodule
