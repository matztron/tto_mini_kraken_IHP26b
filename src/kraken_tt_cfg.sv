// Tiny Tapeout PIO tile — runtime SM configuration (loaded via pins).
module kraken_tt_cfg (
  input  logic       clk,
  input  logic       rst_n,

  input  logic       exec_wr,
  input  logic [7:0] exec_data,
  input  logic       pin_wr,
  input  logic [7:0] pin_data,
  input  logic       shift_wr,
  input  logic [7:0] shift_data,
  input  logic       thresh_wr,
  input  logic [7:0] thresh_data,
  input  logic       inpin_wr,
  input  logic [7:0] inpin_data,
  input  logic       clkdiv_lo_wr,
  input  logic       clkdiv_hi_wr,
  input  logic [7:0] clkdiv_byte,

  output kraken_pkg::pc_t        wrap_bottom,
  output kraken_pkg::pc_t        wrap_top,
  output logic       side_en,
  output logic       side_pindir,
  output logic [2:0] set_count,
  output logic [5:0] out_count,
  output logic [2:0] sideset_count,
  output logic [4:0] in_base,
  output logic [4:0] jmp_pin,
  output logic       in_shiftdir,
  output logic       out_shiftdir,
  output logic       autopush,
  output logic       autopull,
  output logic [4:0] push_thresh,
  output logic [4:0] pull_thresh,
  output logic [15:0] clkdiv_int
);
  typedef kraken_pkg::pc_t pc_t;

  localparam logic [15:0] CLKDIV_RST = 16'd1;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wrap_bottom   <= '0;
      wrap_top      <= '0;
      side_en       <= 1'b0;
      side_pindir   <= 1'b0;
      set_count     <= 3'd0;
      out_count     <= 6'd0;
      sideset_count <= 3'd0;
      in_base       <= 5'd0;
      jmp_pin       <= 5'd0;
      in_shiftdir   <= 1'b0;
      out_shiftdir  <= 1'b1;
      autopush      <= 1'b0;
      autopull      <= 1'b0;
      push_thresh   <= 5'd0;
      pull_thresh   <= 5'd0;
      clkdiv_int    <= CLKDIV_RST;
    end else begin
      if (exec_wr) begin
        wrap_bottom <= kraken_pkg::pc_t'(exec_data[3:0]);
        wrap_top    <= kraken_pkg::pc_t'(exec_data[7:4]);
      end
      if (pin_wr) begin
        set_count     <= {1'b0, pin_data[1:0]};
        out_count     <= {4'b0, pin_data[3:2]};
        sideset_count <= {1'b0, pin_data[5:4]};
        side_pindir   <= pin_data[6];
        side_en       <= pin_data[7];
      end
      if (shift_wr) begin
        in_shiftdir  <= shift_data[0];
        out_shiftdir <= shift_data[1];
        autopush     <= shift_data[2];
        autopull     <= shift_data[3];
      end
      if (thresh_wr) begin
        push_thresh <= thresh_data[4:0];
        pull_thresh <= {2'b0, thresh_data[7:5]};
      end
      if (inpin_wr) begin
        in_base <= inpin_data[4:0];
        jmp_pin <= {3'b0, inpin_data[7:5]};
      end
      if (clkdiv_lo_wr)
        clkdiv_int[7:0]  <= clkdiv_byte;
      if (clkdiv_hi_wr)
        clkdiv_int[15:8] <= clkdiv_byte;
    end
  end
endmodule
