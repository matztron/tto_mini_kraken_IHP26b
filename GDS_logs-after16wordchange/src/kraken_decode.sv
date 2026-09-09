// Combinational instruction decode (PIO 16-bit encoding).
module kraken_decode (
  input  kraken_pkg::instr_t   instr,
  output kraken_pkg::decoded_t dec
);
  always_comb begin
    dec = kraken_pkg::decode_instr(instr);
  end
endmodule
