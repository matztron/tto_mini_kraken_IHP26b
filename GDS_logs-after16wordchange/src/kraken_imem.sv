// Shared instruction memory: 1 write port, 1 read port (TT / Yosys cut).
module kraken_imem (
  input  logic                  clk,
  input  logic                  rst_n,

  // Host program load
  input  logic                  wr_en,
  input  kraken_pkg::pc_t       wr_addr,
  input  kraken_pkg::instr_t    wr_data,

  // State-machine fetch
  input  kraken_pkg::pc_t       rd_addr,
  output kraken_pkg::instr_t    rd_data
);
  typedef kraken_pkg::instr_t instr_t;
  localparam int unsigned IMEM_DEPTH = kraken_pkg::IMEM_DEPTH;

  instr_t mem [IMEM_DEPTH];

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < IMEM_DEPTH; i++) begin
        mem[i] <= '0;
      end
    end else if (wr_en) begin
      mem[wr_addr] <= wr_data;
    end
  end

  assign rd_data = mem[rd_addr];
endmodule
