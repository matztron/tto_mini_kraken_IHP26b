// Scratch + shift registers for one state machine.
module kraken_regfile (
  input  logic   clk,
  input  logic   rst_n,
  input  logic   clear,      // SM_RESTART
  input  logic   tick,       // SM enabled and executing (not in delay)

  input  logic   we_x,
  input  logic   we_y,
  input  logic   we_isr,
  input  logic   we_osr,
  input  kraken_pkg::data_t  wdata_x,
  input  kraken_pkg::data_t  wdata_y,
  input  kraken_pkg::data_t  wdata_isr,
  input  kraken_pkg::data_t  wdata_osr,

  output kraken_pkg::data_t  x,
  output kraken_pkg::data_t  y,
  output kraken_pkg::data_t  isr,
  output kraken_pkg::data_t  osr
);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      x   <= '0;
      y   <= '0;
      isr <= '0;
      osr <= '0;
    end else if (clear) begin
      x   <= '0;
      y   <= '0;
      isr <= '0;
      osr <= '0;
    end else if (tick) begin
      if (we_x)   x   <= wdata_x;
      if (we_y)   y   <= wdata_y;
      if (we_isr) isr <= wdata_isr;
      if (we_osr) osr <= wdata_osr;
    end
  end
endmodule
