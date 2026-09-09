// Pin loader for tt_um_kraken_pio — program IMEM + config over ui/uio.
//
// Config mode: uio[7]=1
//   uio[6:4] op:
//     0 IMEM       uio[3:2]=addr[1:0], uio[1]=half, uio[0]=strobe
//                (pin loader supports 4 IMEM words; latch addr/half while strobe=0)
//     1 EXEC       ui[3:0]=wrap_bottom, ui[7:4]=wrap_top
//     2 PIN        set/out/sideset counts, side_pindir, side_en
//     3 CLKDIV lo
//     4 CLKDIV hi
//     5 SHIFT      shiftdir + autopush/autopull
//     6 THRESH     ui[4:0]=push_thresh, ui[7:5]=pull_thresh[2:0]
//     7 INPIN      ui[4:0]=in_base, ui[7:5]=jmp_pin[2:0]
module kraken_tt_loader (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [7:0] ui_in,
  input  logic [7:0] uio_in,

  output logic       cfg_mode,
  output logic              imem_wr_en,
  output kraken_pkg::pc_t   imem_wr_addr,
  output kraken_pkg::instr_t imem_wr_data,

  output logic       exec_wr,
  output logic [7:0] exec_data,
  output logic       pin_wr,
  output logic [7:0] pin_data,
  output logic       shift_wr,
  output logic [7:0] shift_data,
  output logic       thresh_wr,
  output logic [7:0] thresh_data,
  output logic       inpin_wr,
  output logic [7:0] inpin_data,
  output logic       clkdiv_lo_wr,
  output logic       clkdiv_hi_wr,
  output logic [7:0] clkdiv_byte
);
  typedef kraken_pkg::pc_t    pc_t;
  typedef kraken_pkg::instr_t instr_t;

  localparam logic [2:0] OP_IMEM         = 3'd0;
  localparam logic [2:0] OP_EXEC         = 3'd1;
  localparam logic [2:0] OP_PIN          = 3'd2;
  localparam logic [2:0] OP_CLKDIV_LO    = 3'd3;
  localparam logic [2:0] OP_CLKDIV_HI    = 3'd4;
  localparam logic [2:0] OP_SHIFT        = 3'd5;
  localparam logic [2:0] OP_THRESH       = 3'd6;
  localparam logic [2:0] OP_INPIN        = 3'd7;

  logic        strobe_q;
  logic        strobe_rise;
  logic [7:0]  imem_lo;
  logic [2:0]  op;
  logic [1:0]  imem_addr_q;
  logic        imem_half_q;

  assign cfg_mode    = uio_in[7];
  assign op          = uio_in[6:4];
  assign strobe_rise = uio_in[0] && !strobe_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      strobe_q <= 1'b0;
    else
      strobe_q <= uio_in[0];
  end

  // Latch IMEM addr/half while strobe is low (uio[0] shares addr[0]).
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      imem_addr_q <= '0;
      imem_half_q <= 1'b0;
    end else if (cfg_mode && op == OP_IMEM && !uio_in[0]) begin
      imem_addr_q <= uio_in[3:2];
      imem_half_q <= uio_in[1];
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      imem_lo <= 8'h00;
    end else if (cfg_mode && strobe_rise && op == OP_IMEM && !imem_half_q) begin
      imem_lo <= ui_in;
    end
  end

  always_comb begin
    imem_wr_en       = 1'b0;
    imem_wr_addr     = kraken_pkg::pc_t'({2'b0, imem_addr_q});
    imem_wr_data     = kraken_pkg::instr_t'({ui_in, imem_lo});
    exec_wr          = 1'b0;
    exec_data        = ui_in;
    pin_wr           = 1'b0;
    pin_data         = ui_in;
    shift_wr         = 1'b0;
    shift_data       = ui_in;
    thresh_wr        = 1'b0;
    thresh_data      = ui_in;
    inpin_wr         = 1'b0;
    inpin_data       = ui_in;
    clkdiv_lo_wr     = 1'b0;
    clkdiv_hi_wr     = 1'b0;
    clkdiv_byte      = ui_in;

    if (cfg_mode && strobe_rise) begin
      unique case (op)
        OP_IMEM: begin
          if (imem_half_q)
            imem_wr_en = 1'b1;
        end
        OP_EXEC:         exec_wr        = 1'b1;
        OP_PIN:          pin_wr         = 1'b1;
        OP_CLKDIV_LO:    clkdiv_lo_wr   = 1'b1;
        OP_CLKDIV_HI:    clkdiv_hi_wr   = 1'b1;
        OP_SHIFT:        shift_wr  = 1'b1;
        OP_THRESH:       thresh_wr = 1'b1;
        OP_INPIN:        inpin_wr  = 1'b1;
        default: ;
      endcase
    end
  end
endmodule
