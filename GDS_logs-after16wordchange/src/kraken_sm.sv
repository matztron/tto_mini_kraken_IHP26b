// Kraken PIO state machine — single-cycle execute + delay + stall.
// Tiny Tapeout cut: TX-only FIFO by default (no FJOIN / RX storage).
module kraken_sm #(
  parameter bit ENABLE_FJOIN = 1'b0,
  parameter bit ENABLE_RX    = 1'b0
) (
  input  logic clk,
  input  logic rst_n,
  input  logic enable,
  input  logic clk_en,
  input  logic sm_restart,          // pulse: clear SM + FIFOs
  input  logic                  host_exec_stb,       // pulse: queue SM_INSTR
  input  kraken_pkg::instr_t    host_exec_instr,
  input  logic [1:0]            sm_id,

  input  kraken_pkg::pc_t       wrap_bottom,
  input  kraken_pkg::pc_t       wrap_top,
  input  logic [4:0] set_base,
  input  logic [2:0] set_count,
  input  logic [4:0] out_base,
  input  logic [5:0] out_count,
  input  logic [4:0] in_base,
  input  logic [4:0] jmp_pin,

  input  logic [4:0] sideset_base,
  input  logic [2:0] sideset_count,
  input  logic       side_en,
  input  logic       side_pindir,

  input  logic       in_shiftdir,
  input  logic       out_shiftdir,
  input  logic [4:0] push_thresh,
  input  logic [4:0] pull_thresh,
  input  logic       autopush,
  input  logic       autopull,
  input  logic       fjoin_tx,
  input  logic       fjoin_rx,

  input  logic       status_sel,
  input  logic [3:0] status_n,

  output kraken_pkg::pc_t    imem_addr,
  input  kraken_pkg::instr_t imem_data,

  input  kraken_pkg::gpio_t gpio_in,
  output kraken_pkg::gpio_t gpio_out,
  output kraken_pkg::gpio_t gpio_oe,

  input  logic [kraken_pkg::NUM_IRQ-1:0] irq_flags,
  output logic [kraken_pkg::NUM_IRQ-1:0] irq_set,
  output logic [kraken_pkg::NUM_IRQ-1:0] irq_clr,

  input  logic              tx_push,
  input  kraken_pkg::data_t tx_data,
  output logic              tx_full,
  input  logic              rx_pop,
  output kraken_pkg::data_t rx_data,
  output logic              rx_empty,

  // Host debug / status
  output kraken_pkg::pc_t   dbg_pc,
  output logic [3:0] tx_level_o,
  output logic [3:0] rx_level_o,
  output logic       fdbg_txover,
  output logic       fdbg_txunder,
  output logic       fdbg_rxover,
  output logic       fdbg_rxunder,
  output logic [4:0] dbg_delay,
  output logic       dbg_executing,
  output logic       dbg_stalled
);

  typedef kraken_pkg::instr_t      instr_t;
  typedef kraken_pkg::data_t       data_t;
  typedef kraken_pkg::pc_t         pc_t;
  typedef kraken_pkg::gpio_t      gpio_t;
  typedef kraken_pkg::decoded_t   decoded_t;
  typedef kraken_pkg::opcode_e    opcode_e;
  typedef kraken_pkg::alu_op_e    alu_op_e;
  typedef kraken_pkg::jmp_cond_e  jmp_cond_e;
  typedef kraken_pkg::wait_src_e  wait_src_e;
  typedef kraken_pkg::op_sel_e    op_sel_e;
  typedef kraken_pkg::mov_op_e    mov_op_e;
  typedef kraken_pkg::set_dst_e   set_dst_e;
  typedef kraken_pkg::status_sel_e status_sel_e;
  localparam int unsigned GPIO_W          = kraken_pkg::GPIO_W;
  localparam int unsigned DATA_W          = kraken_pkg::DATA_W;
  localparam int unsigned NUM_IRQ         = kraken_pkg::NUM_IRQ;
  localparam int unsigned FIFO_DEPTH      = kraken_pkg::FIFO_DEPTH;
  localparam int unsigned FIFO_JOIN_DEPTH = kraken_pkg::FIFO_JOIN_DEPTH;

  pc_t pc, next_pc_r, seq_pc, next_pc_c, jmp_target;
  logic [4:0] delay_rem;
  logic pending_exec, host_pending;
  instr_t exec_instr, host_instr, instr;
  decoded_t dec;

  logic active, delaying, do_exec, side_tick, host_force;
  logic stall, jmp_taken, ignore_delay, request_exec;
  instr_t request_exec_instr;

  logic irq_hold;
  logic [2:0] irq_hold_idx;

  assign imem_addr = pc;
  assign instr = host_pending ? host_instr : (pending_exec ? exec_instr : imem_data);
  assign active = enable && clk_en;
  assign delaying = (delay_rem != '0);
  assign host_force = host_pending && !delaying;
  assign do_exec = (active && !delaying) || host_force;
  assign side_tick = do_exec;
  assign dbg_pc = pc;
  assign dbg_delay = delay_rem;
  assign dbg_executing = do_exec && !stall;
  assign dbg_stalled = do_exec && stall;

  kraken_decode u_dec (.instr(instr), .dec(dec));

  logic [4:0] instr_delay, side_imm;
  logic do_side;
  assign instr_delay = kraken_pkg::delay_from_sideset_field(dec.delay_sideset, sideset_count, side_en);
  assign do_side     = kraken_pkg::side_valid_from_field(dec.delay_sideset, sideset_count, side_en);
  assign side_imm    = kraken_pkg::side_data_from_field(dec.delay_sideset, sideset_count, side_en);

  logic we_x, we_y, we_isr, we_osr;
  data_t wdata_x, wdata_y, wdata_isr, wdata_osr, x, y, isr, osr;
  logic [5:0] isr_count, osr_count, wdata_isr_count, wdata_osr_count;
  logic we_isr_count, we_osr_count;

  logic do_set_pins, do_set_pindirs, do_out_pins, do_out_pindirs;
  data_t out_data;
  logic [4:0] set_imm;

  alu_op_e alu_op;
  data_t alu_a, alu_b, alu_y;
  logic alu_z;

  kraken_alu u_alu (.op(alu_op), .a(alu_a), .b(alu_b), .y(alu_y), .z(alu_z));
  kraken_regfile u_rf (
    .clk(clk), .rst_n(rst_n), .clear(sm_restart), .tick(do_exec && !stall),
    .we_x(we_x), .we_y(we_y), .we_isr(we_isr), .we_osr(we_osr),
    .wdata_x(wdata_x), .wdata_y(wdata_y), .wdata_isr(wdata_isr), .wdata_osr(wdata_osr),
    .x(x), .y(y), .isr(isr), .osr(osr)
  );
  kraken_pins u_pins (
    .clk(clk), .rst_n(rst_n),
    .tick(do_exec && !stall), .side_tick(side_tick),
    .set_base(set_base), .set_count(set_count),
    .out_base(out_base), .out_count(out_count),
    .sideset_base(sideset_base), .sideset_count(sideset_count),
    .do_set_pins(do_set_pins), .do_set_pindirs(do_set_pindirs), .set_imm(set_imm),
    .do_out_pins(do_out_pins), .do_out_pindirs(do_out_pindirs), .out_data(out_data),
    .do_side(do_side), .side_pindir(side_pindir), .side_imm(side_imm),
    .gpio_out(gpio_out), .gpio_oe(gpio_oe)
  );

  logic use_join_tx, use_join_rx;
  assign use_join_tx = ENABLE_FJOIN && fjoin_tx && !fjoin_rx;
  assign use_join_rx = ENABLE_FJOIN && fjoin_rx && !fjoin_tx;

  logic sm_rx_push, sm_tx_pop;
  data_t sm_rx_data, tx_pop_data;
  logic rx_full, tx_empty;
  logic [$clog2(FIFO_JOIN_DEPTH+1)-1:0] tx_level, rx_level;

  logic tx4_push, tx4_pop, tx4_full, tx4_empty;
  data_t tx4_push_data, tx4_pop_data;
  logic [$clog2(FIFO_DEPTH+1)-1:0] tx4_level;

  logic rx4_push, rx4_pop, rx4_full, rx4_empty;
  data_t rx4_push_data, rx4_pop_data;
  logic [$clog2(FIFO_DEPTH+1)-1:0] rx4_level;

  logic j_push, j_pop, j_full, j_empty;
  data_t j_push_data, j_pop_data;
  logic [$clog2(FIFO_JOIN_DEPTH+1)-1:0] j_level;

  kraken_fifo #(.DEPTH(FIFO_DEPTH)) u_tx (
    .clk(clk), .rst_n(rst_n), .clear(sm_restart),
    .push(tx4_push), .push_data(tx4_push_data), .full(tx4_full),
    .pop(tx4_pop), .pop_data(tx4_pop_data), .empty(tx4_empty), .level(tx4_level)
  );

  if (ENABLE_RX) begin : g_rx
    kraken_fifo #(.DEPTH(FIFO_DEPTH)) u_rx (
      .clk(clk), .rst_n(rst_n), .clear(sm_restart),
      .push(rx4_push), .push_data(rx4_push_data), .full(rx4_full),
      .pop(rx4_pop), .pop_data(rx4_pop_data), .empty(rx4_empty), .level(rx4_level)
    );
  end else begin : g_no_rx
    assign rx4_full  = 1'b1;
    assign rx4_empty = 1'b1;
    assign rx4_pop_data = '0;
    assign rx4_level = '0;
  end

  if (ENABLE_FJOIN) begin : g_join
    kraken_fifo #(.DEPTH(FIFO_JOIN_DEPTH)) u_join (
      .clk(clk), .rst_n(rst_n), .clear(sm_restart),
      .push(j_push), .push_data(j_push_data), .full(j_full),
      .pop(j_pop), .pop_data(j_pop_data), .empty(j_empty), .level(j_level)
    );
  end else begin : g_no_join
    assign j_full  = 1'b1;
    assign j_empty = 1'b1;
    assign j_pop_data = '0;
    assign j_level = '0;
  end

  logic normal_fifos;
  assign normal_fifos = !use_join_tx && !use_join_rx;

  assign tx4_push      = normal_fifos ? tx_push : 1'b0;
  assign tx4_push_data = tx_data;
  assign tx4_pop       = normal_fifos ? sm_tx_pop : 1'b0;

  assign rx4_push      = (ENABLE_RX && normal_fifos) ? sm_rx_push : 1'b0;
  assign rx4_push_data = sm_rx_data;
  assign rx4_pop       = (ENABLE_RX && normal_fifos) ? rx_pop : 1'b0;

  assign j_push      = use_join_tx ? tx_push : (use_join_rx ? sm_rx_push : 1'b0);
  assign j_push_data = use_join_tx ? tx_data : sm_rx_data;
  assign j_pop       = use_join_tx ? sm_tx_pop : (use_join_rx ? rx_pop : 1'b0);

  assign tx_full     = use_join_rx ? 1'b1 : (use_join_tx ? j_full  : tx4_full);
  assign tx_empty    = use_join_rx ? 1'b1 : (use_join_tx ? j_empty : tx4_empty);
  assign tx_pop_data = use_join_tx ? j_pop_data : tx4_pop_data;
  assign tx_level    = use_join_tx ? j_level
                     : (use_join_rx ? '0
                     : {{($clog2(FIFO_JOIN_DEPTH+1)-$clog2(FIFO_DEPTH+1)){1'b0}}, tx4_level});

  assign rx_full  = use_join_tx ? 1'b1 : (use_join_rx ? j_full  : rx4_full);
  assign rx_empty = use_join_tx ? 1'b1 : (use_join_rx ? j_empty : rx4_empty);
  assign rx_data  = use_join_rx ? j_pop_data : rx4_pop_data;
  assign rx_level = use_join_rx ? j_level
                    : (use_join_tx ? '0
                    : {{($clog2(FIFO_JOIN_DEPTH+1)-$clog2(FIFO_DEPTH+1)){1'b0}}, rx4_level});

  assign tx_level_o = 4'(tx_level);
  assign rx_level_o = 4'(rx_level);

  assign fdbg_txover  = tx_push && tx_full;
  assign fdbg_rxunder = rx_pop && rx_empty;
  logic sm_txunder_ev, sm_rxover_ev;
  assign fdbg_txunder = sm_txunder_ev;
  assign fdbg_rxover  = sm_rxover_ev;

  logic [5:0] push_th, pull_th;
  logic osr_empty;
  data_t status_val;
  assign push_th   = kraken_pkg::thresh_decode(push_thresh);
  assign pull_th   = kraken_pkg::thresh_decode(pull_thresh);
  assign osr_empty = (osr_count >= pull_th);
  assign status_val = ((status_sel == kraken_pkg::STATUS_RXLEVEL ? rx_level : tx_level) < status_n)
                      ? '1 : '0;

  function automatic data_t pins_bus();
    data_t b;
    integer i;
    integer idx;
    begin
      b = '0;
      for (i = 0; i < DATA_W; i = i + 1) begin
        idx = in_base + i;
        if (idx < GPIO_W) b[i] = gpio_in[idx];
      end
      pins_bus = b;
    end
  endfunction

  function automatic logic [2:0] irq_idx_f(input logic [4:0] raw);
    logic [2:0] idx;
    begin
      idx = raw[2:0];
      if (raw[4]) idx[1:0] = idx[1:0] + sm_id;
      irq_idx_f = idx;
    end
  endfunction

  data_t in_bits, cur_osr, taken, src_v, val;
  logic [5:0] nbits, cur_cnt;
  logic [2:0] iidx;

  always_comb begin
    we_x = 0; we_y = 0; we_isr = 0; we_osr = 0;
    wdata_x = x; wdata_y = y; wdata_isr = isr; wdata_osr = osr;
    we_isr_count = 0; we_osr_count = 0;
    wdata_isr_count = isr_count; wdata_osr_count = osr_count;
    do_set_pins = 0; do_set_pindirs = 0; do_out_pins = 0; do_out_pindirs = 0;
    out_data = '0; set_imm = dec.arg2;
    alu_op = kraken_pkg::ALU_PASS_A; alu_a = x; alu_b = '0;
    sm_rx_push = 0; sm_rx_data = isr; sm_tx_pop = 0;
    irq_set = '0; irq_clr = '0;
    stall = 0; jmp_taken = 0; jmp_target = kraken_pkg::pc_t'(dec.arg2);
    ignore_delay = host_pending; request_exec = 0; request_exec_instr = '0;
    in_bits = '0; cur_osr = osr; taken = '0; src_v = '0; val = '0;
    nbits = '0; cur_cnt = osr_count; iidx = '0;
    sm_txunder_ev = 0; sm_rxover_ev = 0;

    seq_pc = (pc == wrap_top) ? wrap_bottom : (pc + kraken_pkg::pc_t'(1));

    if (irq_hold) stall = irq_flags[irq_hold_idx];

    if (do_exec && !irq_hold) begin
      nbits = kraken_pkg::bit_count_decode(dec.arg2);
      iidx  = irq_idx_f(dec.arg2);

      unique case (dec.opcode)
        kraken_pkg::OPC_JMP: begin
          unique case (dec.arg1)
            kraken_pkg::JMP_ALWAYS: jmp_taken = 1;
            kraken_pkg::JMP_NOT_X:  jmp_taken = (x == '0);
            kraken_pkg::JMP_X_DEC: if (x != '0) begin
              jmp_taken = 1; we_x = 1; wdata_x = x - kraken_pkg::data_t'(1);
            end
            kraken_pkg::JMP_NOT_Y: jmp_taken = (y == '0);
            kraken_pkg::JMP_Y_DEC: if (y != '0) begin
              jmp_taken = 1; we_y = 1; wdata_y = y - kraken_pkg::data_t'(1);
            end
            kraken_pkg::JMP_X_NE_Y:   jmp_taken = (x != y);
            kraken_pkg::JMP_PIN:      jmp_taken = (jmp_pin < GPIO_W) ? gpio_in[jmp_pin] : 1'b0;
            kraken_pkg::JMP_NOT_OSRE: jmp_taken = osr_empty;
            default: ;
          endcase
        end

        kraken_pkg::OPC_WAIT: begin
          unique case (dec.arg1[1:0])
            kraken_pkg::WAIT_GPIO: stall = (dec.arg2 < GPIO_W) ? (gpio_in[dec.arg2] != dec.arg1[2]) : 1'b1;
            kraken_pkg::WAIT_PIN: begin
              if (5'(in_base + dec.arg2) < GPIO_W)
                stall = (gpio_in[5'(in_base + dec.arg2)] != dec.arg1[2]);
              else
                stall = 1'b1;
            end
            kraken_pkg::WAIT_IRQ:  stall = (iidx < NUM_IRQ) && (irq_flags[iidx] != dec.arg1[2]);
            default: ;
          endcase
        end

        kraken_pkg::OPC_IN: begin
          unique case (dec.arg1)
            kraken_pkg::OP_PINS: in_bits = pins_bus();
            kraken_pkg::OP_X:    in_bits = x;
            kraken_pkg::OP_Y:    in_bits = y;
            kraken_pkg::OP_NULL: in_bits = '0;
            kraken_pkg::OP_ISR:  in_bits = isr;
            kraken_pkg::OP_OSR:  in_bits = osr;
            default: in_bits = '0;
          endcase
          if (nbits < 6'(DATA_W)) in_bits = in_bits & ((kraken_pkg::data_t'(1) << nbits) - 1);
          we_isr = 1;
          wdata_isr = kraken_pkg::isr_shift_in(isr, in_bits, nbits, in_shiftdir);
          we_isr_count = 1;
          wdata_isr_count = (isr_count + nbits > 6'(DATA_W)) ? 6'(DATA_W) : isr_count + nbits;
          if (autopush && wdata_isr_count >= push_th) begin
            if (rx_full) begin stall = 1; sm_rxover_ev = 1; end
            else begin
              sm_rx_push = 1; sm_rx_data = wdata_isr;
              wdata_isr = '0; wdata_isr_count = '0;
            end
          end
        end

        kraken_pkg::OPC_OUT: begin
          cur_osr = osr;
          cur_cnt = osr_count;
          if (autopull && osr_empty) begin
            if (tx_empty) begin stall = 1; sm_txunder_ev = 1; end
            else begin sm_tx_pop = 1; cur_osr = tx_pop_data; cur_cnt = '0; end
          end
          if (!stall) begin
            taken = kraken_pkg::osr_take(cur_osr, nbits, out_shiftdir);
            we_osr = 1;
            wdata_osr = kraken_pkg::osr_shifted(cur_osr, nbits, out_shiftdir);
            we_osr_count = 1;
            wdata_osr_count = (cur_cnt + nbits > 6'(DATA_W)) ? 6'(DATA_W) : cur_cnt + nbits;
            unique case (dec.arg1)
              kraken_pkg::OP_PINS: begin do_out_pins = 1; out_data = taken; end
              kraken_pkg::OP_X: begin we_x = 1; wdata_x = taken; end
              kraken_pkg::OP_Y: begin we_y = 1; wdata_y = taken; end
              kraken_pkg::OP_NULL: ;
              kraken_pkg::OP_PINDIRS: begin do_out_pindirs = 1; out_data = taken; end
              kraken_pkg::OP_PC_STAT: begin jmp_taken = 1; jmp_target = kraken_pkg::pc_t'(taken); end
              kraken_pkg::OP_ISR: begin we_isr = 1; wdata_isr = taken; end
              kraken_pkg::OP_OSR: begin
                request_exec = 1;
                request_exec_instr = kraken_pkg::instr_t'(taken);
                ignore_delay = 1;
              end
              default: ;
            endcase
          end
        end

        kraken_pkg::OPC_PUSH_PULL: begin
          if (!dec.is_pull) begin
            if (!dec.arg1[1] || isr_count >= push_th) begin
              if (rx_full) begin
                sm_rxover_ev = 1;
                if (dec.arg1[0]) stall = 1;
              end else begin
                sm_rx_push = 1; sm_rx_data = isr;
                we_isr = 1; wdata_isr = '0;
                we_isr_count = 1; wdata_isr_count = '0;
              end
            end
          end else begin
            if (!dec.arg1[1] || osr_empty) begin
              if (tx_empty) begin
                sm_txunder_ev = 1;
                if (dec.arg1[0]) stall = 1;
                else begin we_osr = 1; wdata_osr = x; we_osr_count = 1; wdata_osr_count = '0; end
              end else begin
                sm_tx_pop = 1;
                we_osr = 1; wdata_osr = tx_pop_data;
                we_osr_count = 1; wdata_osr_count = '0;
              end
            end
          end
        end

        kraken_pkg::OPC_MOV: begin
          unique case (instr[2:0])
            kraken_pkg::OP_PINS: src_v = pins_bus();
            kraken_pkg::OP_X: src_v = x;
            kraken_pkg::OP_Y: src_v = y;
            kraken_pkg::OP_NULL: src_v = '0;
            kraken_pkg::OP_PC_STAT: src_v = status_val;
            kraken_pkg::OP_ISR: src_v = isr;
            kraken_pkg::OP_OSR: src_v = osr;
            default: src_v = '0;
          endcase
          unique case (instr[4:3])
            kraken_pkg::MOV_INVERT: val = ~src_v;
            kraken_pkg::MOV_REVERSE: val = kraken_pkg::bit_reverse32(src_v);
            default: val = src_v;
          endcase
          unique case (instr[7:5])
            kraken_pkg::OP_PINS: begin do_out_pins = 1; out_data = val; end
            kraken_pkg::OP_X: begin we_x = 1; wdata_x = val; end
            kraken_pkg::OP_Y: begin we_y = 1; wdata_y = val; end
            kraken_pkg::OP_PINDIRS: begin
              request_exec = 1;
              request_exec_instr = kraken_pkg::instr_t'(val);
              ignore_delay = 1;
            end
            kraken_pkg::OP_PC_STAT: begin jmp_taken = 1; jmp_target = kraken_pkg::pc_t'(val); end
            kraken_pkg::OP_ISR: begin we_isr = 1; wdata_isr = val; end
            kraken_pkg::OP_OSR: begin we_osr = 1; wdata_osr = val; end
            default: ;
          endcase
        end

        kraken_pkg::OPC_IRQ: begin
          if (iidx < NUM_IRQ) begin
            if (dec.arg1[1]) irq_clr[iidx] = 1;
            else             irq_set[iidx] = 1;
            if (dec.arg1[0]) begin
              if (dec.arg1[1]) stall = irq_flags[iidx];
              else             stall = 1'b1;
            end
          end
        end

        kraken_pkg::OPC_SET: begin
          unique case (dec.arg1)
            kraken_pkg::SET_DST_PINS: do_set_pins = 1;
            kraken_pkg::SET_DST_X: begin we_x = 1; wdata_x = kraken_pkg::data_t'(dec.arg2); end
            kraken_pkg::SET_DST_Y: begin we_y = 1; wdata_y = kraken_pkg::data_t'(dec.arg2); end
            kraken_pkg::SET_DST_PINDIRS: do_set_pindirs = 1;
            default: ;
          endcase
        end

        default: ;
      endcase
    end

    if (host_pending)
      next_pc_c = jmp_taken ? jmp_target : pc;
    else
      next_pc_c = jmp_taken ? jmp_target : seq_pc;
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      pc <= '0;
      delay_rem <= '0;
      next_pc_r <= '0;
      isr_count <= '0;
      osr_count <= 6'(DATA_W);
      pending_exec <= 0;
      exec_instr <= '0;
      host_pending <= 0;
      host_instr <= '0;
      irq_hold <= 0;
      irq_hold_idx <= '0;
    end else if (sm_restart) begin
      pc <= '0;
      delay_rem <= '0;
      next_pc_r <= '0;
      isr_count <= '0;
      osr_count <= 6'(DATA_W);
      pending_exec <= 0;
      exec_instr <= '0;
      host_pending <= 0;
      host_instr <= '0;
      irq_hold <= 0;
      irq_hold_idx <= '0;
    end else begin
      if (host_exec_stb) begin
        host_pending <= 1'b1;
        host_instr   <= host_exec_instr;
      end

      if (active) begin
        if (delaying) begin
          delay_rem <= delay_rem - 5'd1;
          if (delay_rem == 5'd1) pc <= next_pc_r;
        end else if (do_exec) begin
          if (!irq_hold && dec.opcode == kraken_pkg::OPC_IRQ && dec.arg1[0] && !dec.arg1[1]) begin
            irq_hold <= 1;
            irq_hold_idx <= irq_idx_f(dec.arg2);
          end
          if (irq_hold && !irq_flags[irq_hold_idx]) begin
            irq_hold <= 0;
          end

          if (!stall) begin
            if (we_isr_count) isr_count <= wdata_isr_count;
            if (we_osr_count) osr_count <= wdata_osr_count;

            if (host_pending) begin
              if (!host_exec_stb) host_pending <= 1'b0;
              pending_exec <= 0;
            end else if (request_exec) begin
              pending_exec <= 1;
              exec_instr <= request_exec_instr;
            end else begin
              pending_exec <= 0;
            end

            next_pc_r <= next_pc_c;
            if (!ignore_delay && instr_delay != '0) delay_rem <= instr_delay;
            else pc <= next_pc_c;
          end else if (irq_hold && !irq_flags[irq_hold_idx]) begin
            irq_hold <= 0;
            pending_exec <= 0;
            next_pc_r <= next_pc_c;
            if (!ignore_delay && instr_delay != '0) delay_rem <= instr_delay;
            else pc <= next_pc_c;
          end
        end
      end else if (host_force) begin
        if (!stall) begin
          if (we_isr_count) isr_count <= wdata_isr_count;
          if (we_osr_count) osr_count <= wdata_osr_count;
          if (!host_exec_stb) host_pending <= 1'b0;
          pending_exec <= 0;
          pc <= next_pc_c;
        end
      end
    end
  end
endmodule
