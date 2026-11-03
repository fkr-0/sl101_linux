#include "../grate_compiler.h"
#include "fpir.h"

#include "tgsi/tgsi_parse.h"

#include "util/u_memory.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

struct fp_temp_alias {
   bool valid;
   struct tgsi_src_register src;
   unsigned component;
};

struct fp_pending_tex {
   bool valid;
   unsigned component_mask;
   struct tgsi_src_register coord;
   unsigned sampler_index;
};

struct fp_lowering_state {
   unsigned declared_temps;
   struct fp_temp_alias temp_alias[FP_GPR_COUNT];
   struct fp_pending_tex pending_tex[FP_GPR_COUNT / 4];
};

static bool
fp_fail(struct grate_fp_shader *fp, const char *fmt, ...)
{
   if (!fp->failed) {
      va_list ap;
      va_start(ap, fmt);
      vsnprintf(fp->error, sizeof(fp->error), fmt, ap);
      va_end(ap);
   }

   fp->failed = true;
   return false;
}

static struct fp_alu_src_operand
fp_src_row(unsigned index)
{
   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = FP_ROW_REG_BASE + index,
   };
}

static struct fp_alu_src_operand
fp_src_gpr(unsigned scalar)
{
   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = FP_GPR_BASE + scalar,
   };
}

static struct fp_alu_src_operand
fp_src_texel(unsigned component, unsigned base_reg)
{
   assert(base_reg == 0 || base_reg == 2);

   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = base_reg + component / 2,
      .datatype = FP_DATATYPE_FIXED10,
      .sub_reg_select_high = component & 1,
   };
}

static struct fp_alu_src_operand
fp_src_uniform(unsigned scalar)
{
   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = FP_UNIFORM_BASE + scalar,
   };
}

static struct fp_alu_src_operand
fp_src_zero(void)
{
   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = FP_LOWP_CONST_REG,
      .datatype = FP_DATATYPE_FIXED10,
      .sub_reg_select_high = false,
   };
}

static struct fp_alu_src_operand
fp_src_one(void)
{
   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = FP_LOWP_CONST_REG,
      .datatype = FP_DATATYPE_FIXED10,
      .sub_reg_select_high = true,
   };
}

static struct fp_alu_src_operand
fp_src_disabled_one(void)
{
   struct fp_alu_src_operand src = fp_src_one();
   /*
    * rD has only rB/rC selectors. With rD disabled the hardware supplies 1.0,
    * which is the form required for A*B + C.
    */
   src.enable = false;
   return src;
}

static bool
fp_dst_component(struct grate_fp_shader *fp,
                 const struct tgsi_dst_register *dst,
                 unsigned component, bool saturate,
                 struct fp_alu_dst_operand *out)
{
   memset(out, 0, sizeof(*out));
   out->saturate = saturate;

   switch (dst->File) {
   case TGSI_FILE_TEMPORARY: {
      unsigned scalar = dst->Index * 4 + component;
      if (scalar >= FP_GPR_COUNT)
         return fp_fail(fp,
                        "fragment temporary TEMP[%u].%u exceeds %u FP20 GPR scalars",
                        dst->Index, component, FP_GPR_COUNT);
      out->index = FP_GPR_BASE + scalar;
      /* Both halves select an FP20 destination. */
      out->write_low_sub_reg = true;
      out->write_high_sub_reg = true;
      return true;
   }

   case TGSI_FILE_OUTPUT: {
      if (dst->Index >= 15)
         return fp_fail(fp, "fragment output %u exceeds render-target range",
                        dst->Index);

      /*
       * DW consumes semantic RGBA in r2+r3.  The render-target pixel format
       * performs the memory-layout conversion (for example BGRA8888 storage).
       * Direct TEX->DW hardware proof and ALU color readback both show that
       * pre-swizzling ALU outputs here would swap R/B a second time.
       */
      out->index = 2 + component / 2;
      out->write_low_sub_reg = (component & 1) == 0;
      out->write_high_sub_reg = (component & 1) != 0;
      return true;
   }

   default:
      return fp_fail(fp, "unsupported fragment destination file %u", dst->File);
   }
}

static bool
fp_packet_immediate(struct grate_fp_shader *fp,
                    struct fp_alu_instr_packet *packet,
                    float value, struct fp_alu_src_operand *out)
{
   if (value == 0.0f) {
      *out = fp_src_zero();
      return true;
   }

   if (value == 1.0f) {
      *out = fp_src_one();
      return true;
   }

   uint32_t encoded;
   if (!grate_fp_try_encode_fp20(value, &encoded))
      return fp_fail(fp, "fragment immediate %.9g is not representable as finite FP20",
                     value);

   for (unsigned i = 0; i < FP_EMBEDDED_CONST_COUNT; ++i) {
      if (packet->embedded_constant_used[i] &&
          packet->embedded_constant_fp20[i] == encoded) {
         *out = (struct fp_alu_src_operand) {
            .enable = true,
            .index = FP_EMBEDDED_CONST_BASE + i,
         };
         return true;
      }
   }

   for (unsigned i = 0; i < FP_EMBEDDED_CONST_COUNT; ++i) {
      if (packet->embedded_constant_used[i])
         continue;

      packet->embedded_constant_used[i] = true;
      packet->embedded_constant_fp20[i] = encoded;
      packet->uses_embedded_constants = true;
      *out = (struct fp_alu_src_operand) {
         .enable = true,
         .index = FP_EMBEDDED_CONST_BASE + i,
      };
      return true;
   }

   return fp_fail(fp, "fragment ALU packet requires more than three embedded FP20 constants");
}

static unsigned
fp_src_swizzle(const struct tgsi_src_register *src, unsigned component)
{
   const unsigned swizzle[4] = {
      src->SwizzleX, src->SwizzleY, src->SwizzleZ, src->SwizzleW
   };
   return swizzle[component];
}

static bool
fp_src_component(struct grate_fp_shader *fp,
                 struct fp_lowering_state *lowering,
                 struct fp_alu_instr_packet *packet,
                 struct fp_mfu_instr *mfu,
                 int varying_rows[4],
                 const struct tgsi_src_register *src,
                 unsigned component,
                 struct fp_alu_src_operand *out,
                 bool *uses_mfu,
                 int *tex_temp_index)
{
   unsigned swizzle = fp_src_swizzle(src, component);
   if (swizzle > 3)
      return fp_fail(fp, "invalid fragment swizzle component %u", swizzle);

   switch (src->File) {
   case TGSI_FILE_INPUT:
      if (src->Index >= FP_ROW_REG_COUNT)
         return fp_fail(fp, "fragment INPUT[%u] exceeds 16 TRAM rows", src->Index);

      if (varying_rows[swizzle] >= 0 &&
          varying_rows[swizzle] != (int)src->Index) {
         /*
          * One MFU VAR slot can select only one TRAM row for a component in
          * one EXEC.  Callers must materialize one varying in an earlier
          * EXEC/GPR rather than alias two rows here.
          */
         return fp_fail(fp,
                        "fragment ALU packet needs INPUT[%d] and INPUT[%u] in row component %u",
                        varying_rows[swizzle], src->Index, swizzle);
      }

      varying_rows[swizzle] = src->Index;
      mfu->var[swizzle].op = FP_VAR_OP_FP20;
      mfu->var[swizzle].tram_row = src->Index;
      if ((int)src->Index + 1 > fp->info.max_tram_row)
         fp->info.max_tram_row = src->Index + 1;
      *uses_mfu = true;
      *out = fp_src_row(swizzle);
      break;

   case TGSI_FILE_TEMPORARY: {
      unsigned scalar = src->Index * 4 + swizzle;
      if (scalar >= FP_GPR_COUNT)
         return fp_fail(fp,
                        "fragment TEMP[%u].%u exceeds %u FP20 GPR scalars",
                        src->Index, swizzle, FP_GPR_COUNT);

      /*
       * Mesa frequently constructs a vec4 TEMP from a varying plus 0/1 and
       * immediately consumes it in arithmetic.  Keeping that TEMP in GPRs
       * crosses PSEQ EXEC recirculation; live Tegra20 qualification showed
       * those values are not reliable in the later arithmetic EXECs.  Fold
       * only simple MOV aliases back to their original scalar source so MFU
       * interpolation and ALU consumption happen in the same EXEC.
       */
      if (lowering->temp_alias[scalar].valid) {
         const struct fp_temp_alias *alias = &lowering->temp_alias[scalar];
         if (!fp_src_component(fp, lowering, packet, mfu, varying_rows,
                               &alias->src, alias->component,
                               out, uses_mfu, tex_temp_index))
            return false;
         /* Aliases are created only from unmodified MOV sources. Apply the
          * current consumer's modifiers to the resolved physical operand.
          */
         out->negate = src->Negate;
         out->absolute_value = src->Absolute;
         return true;
      }

      if (src->Index < FP_GPR_COUNT / 4) {
         const struct fp_pending_tex *pending =
            &lowering->pending_tex[src->Index];

         if (pending->valid &&
             (pending->component_mask & (1u << swizzle))) {
            if (*tex_temp_index >= 0 &&
                *tex_temp_index != (int)src->Index)
               return fp_fail(fp,
                              "fragment ALU packet needs two pending texture temporaries");

            *tex_temp_index = src->Index;
            *out = fp_src_texel(swizzle, 0);
            break;
         }
      }

      *out = fp_src_gpr(scalar);
      break;
   }

   case TGSI_FILE_CONSTANT: {
      unsigned scalar = src->Index * 4 + swizzle;
      if (scalar >= FP_UNIFORM_COUNT)
         return fp_fail(fp,
                        "fragment CONST[%u].%u exceeds %u scalar FP20 uniforms",
                        src->Index, swizzle, FP_UNIFORM_COUNT);
      *out = fp_src_uniform(scalar);
      break;
   }

   case TGSI_FILE_IMMEDIATE:
      if ((unsigned)src->Index >= fp->num_immediates)
         return fp_fail(fp, "fragment immediate index %u is not declared", src->Index);
      if (!fp_packet_immediate(fp, packet,
                               fp->immediates[src->Index][swizzle], out))
         return false;
      break;

   default:
      return fp_fail(fp, "unsupported fragment source file %u", src->File);
   }

   out->negate = src->Negate;
   out->absolute_value = src->Absolute;
   return true;
}

static struct fp_alu_instr
fp_make_mov(struct fp_alu_dst_operand dst, struct fp_alu_src_operand src)
{
   return (struct fp_alu_instr) {
      .op = FP_ALU_OP_MAD,
      .dst = dst,
      .src = { src, fp_src_one(), fp_src_zero(), fp_src_disabled_one() },
   };
}

static struct fp_alu_instr
fp_make_add(struct fp_alu_dst_operand dst,
            struct fp_alu_src_operand a, struct fp_alu_src_operand b)
{
   return (struct fp_alu_instr) {
      .op = FP_ALU_OP_MAD,
      .dst = dst,
      .src = { a, fp_src_one(), b, fp_src_disabled_one() },
   };
}

static struct fp_alu_instr
fp_make_mul(struct fp_alu_dst_operand dst,
            struct fp_alu_src_operand a, struct fp_alu_src_operand b)
{
   /*
    * A regular FP20 multiply is MAD(a, b, 0).  Tegra20's
    * addition-disable bit selects the special dual-FX10 multiply mode;
    * it is not the FP20 "omit addend" encoding.
    */

   return (struct fp_alu_instr) {
      .op = FP_ALU_OP_MAD,
      .dst = dst,
      .src = { a, b, fp_src_zero(), fp_src_disabled_one() },
   };
}

static struct fp_alu_instr
fp_make_mad(struct fp_alu_dst_operand dst,
            struct fp_alu_src_operand a, struct fp_alu_src_operand b,
            struct fp_alu_src_operand c)
{
   return (struct fp_alu_instr) {
      .op = FP_ALU_OP_MAD,
      .dst = dst,
      .src = { a, b, c, fp_src_disabled_one() },
   };
}

static struct fp_alu_instr
fp_make_min(struct fp_alu_dst_operand dst,
            struct fp_alu_src_operand a, struct fp_alu_src_operand b)
{
   return (struct fp_alu_instr) {
      .op = FP_ALU_OP_MIN,
      .dst = dst,
      .src = { a, b, fp_src_zero(), fp_src_disabled_one() },
   };
}

static struct fp_alu_instr
fp_make_max(struct fp_alu_dst_operand dst,
            struct fp_alu_src_operand a, struct fp_alu_src_operand b)
{
   return (struct fp_alu_instr) {
      .op = FP_ALU_OP_MAX,
      .dst = dst,
      .src = { a, b, fp_src_zero(), fp_src_disabled_one() },
   };
}

static bool
fp_instruction_uses_embedded(const struct grate_fp_shader *fp,
                             const struct tgsi_full_instruction *inst)
{
   for (unsigned s = 0; s < inst->Instruction.NumSrcRegs; ++s) {
      const struct tgsi_src_register *src = &inst->Src[s].Register;
      if (src->File != TGSI_FILE_IMMEDIATE ||
          (unsigned)src->Index >= fp->num_immediates)
         continue;

      for (unsigned c = 0; c < 4; ++c) {
         if (!(inst->Dst[0].Register.WriteMask & (1u << c)))
            continue;
         float value = fp->immediates[src->Index][fp_src_swizzle(src, c)];
         if (value != 0.0f && value != 1.0f)
            return true;
      }
   }

   return false;
}

static void
fp_note_dw_exec(struct grate_fp_shader *fp)
{
   const unsigned exec_nb = list_length(&fp->fp_instructions) + 1;
   if (exec_nb > fp->info.pseq_to_dw_exec_nb)
      fp->info.pseq_to_dw_exec_nb = exec_nb;
}

static bool
fp_find_two_input_row_conflict(const struct tgsi_full_instruction *inst,
                               unsigned component,
                               unsigned *first_src, unsigned *second_src,
                               unsigned *swizzle)
{
   if (inst->Instruction.NumSrcRegs != 2)
      return false;

   const struct tgsi_src_register *a = &inst->Src[0].Register;
   const struct tgsi_src_register *b = &inst->Src[1].Register;
   if (a->File != TGSI_FILE_INPUT || b->File != TGSI_FILE_INPUT ||
       a->Negate || a->Absolute || b->Negate || b->Absolute)
      return false;

   unsigned as = fp_src_swizzle(a, component);
   unsigned bs = fp_src_swizzle(b, component);
   if (as != bs || a->Index == b->Index)
      return false;

   *first_src = 0;
   *second_src = 1;
   *swizzle = as;
   return true;
}

static bool
fp_emit_two_input_row_conflict(struct grate_fp_shader *fp,
                               const struct tgsi_full_instruction *tgsi_inst,
                               unsigned component,
                               unsigned first_src, unsigned second_src,
                               unsigned swizzle, bool saturate)
{
   const struct tgsi_dst_register *dst = &tgsi_inst->Dst[0].Register;
   const struct tgsi_src_register *a = &tgsi_inst->Src[first_src].Register;
   const struct tgsi_src_register *b = &tgsi_inst->Src[second_src].Register;

   if (tgsi_inst->Instruction.Opcode != TGSI_OPCODE_ADD &&
       tgsi_inst->Instruction.Opcode != TGSI_OPCODE_MUL)
      return fp_fail(fp, "two-varying row conflict currently supports ADD/MUL only");
   if (a->Index >= FP_ROW_REG_COUNT || b->Index >= FP_ROW_REG_COUNT)
      return fp_fail(fp, "two-varying row conflict exceeds TRAM row range");
   if (list_length(&fp->fp_instructions) >= 63 ||
       list_length(&fp->mfu_instructions) > 61 ||
       list_length(&fp->alu_instructions) > 61)
      return fp_fail(fp, "two-varying row conflict exceeds scheduling limits");

   struct fp_instr *inst = CALLOC_STRUCT(fp_instr);
   struct fp_mfu_instr *mfu0 = CALLOC_STRUCT(fp_mfu_instr);
   struct fp_mfu_instr *mfu1 = CALLOC_STRUCT(fp_mfu_instr);
   struct fp_alu_instr_packet *alu = CALLOC_STRUCT(fp_alu_instr_packet);
   if (!inst || !mfu0 || !mfu1 || !alu) {
      FREE(inst); FREE(mfu0); FREE(mfu1); FREE(alu);
      return fp_fail(fp, "out of memory lowering two-varying row conflict");
   }

   list_inithead(&inst->link);
   list_inithead(&mfu0->link); list_inithead(&mfu1->link);
   list_inithead(&alu->link);

   mfu0->var[swizzle].op = FP_VAR_OP_FP20;
   mfu0->var[swizzle].tram_row = a->Index;
   mfu1->var[swizzle].op = FP_VAR_OP_FP20;
   mfu1->var[swizzle].tram_row = b->Index;
   if ((int)a->Index + 1 > fp->info.max_tram_row)
      fp->info.max_tram_row = a->Index + 1;
   if ((int)b->Index + 1 > fp->info.max_tram_row)
      fp->info.max_tram_row = b->Index + 1;

   /*
    * Keep both varying values inside MFU row registers.  MFU0 interpolates
    * row A into the requested component register.  MFU1 first copies that
    * register into a spare row register using *1, then overwrites the original
    * component register with row B.  This avoids both GPR lifetime assumptions
    * and a PSEQ recirculation boundary.
    */
   const unsigned scratch_row = (swizzle + 1) & 3;
   mfu1->mul[0].dst = FP_MFU_MUL_DST_ROW_REG_0 + scratch_row;
   mfu1->mul[0].src[0] = FP_MFU_MUL_SRC_ROW_REG_0 + swizzle;
   mfu1->mul[0].src[1] = FP_MFU_MUL_SRC_CONST_1;

   struct fp_alu_dst_operand d;
   if (!fp_dst_component(fp, dst, component, saturate, &d)) {
      FREE(inst); FREE(mfu0); FREE(mfu1); FREE(alu);
      return false;
   }
   struct fp_alu_src_operand left = fp_src_row(scratch_row);
   struct fp_alu_src_operand right = fp_src_row(swizzle);
   if (tgsi_inst->Instruction.Opcode == TGSI_OPCODE_ADD)
      alu->slots[0] = fp_make_add(d, left, right);
   else
      alu->slots[0] = fp_make_mul(d, left, right);

   inst->mfu_sched.address = list_length(&fp->mfu_instructions);
   inst->mfu_sched.num_instructions = 2;
   inst->alu_sched.address = list_length(&fp->alu_instructions);
   inst->alu_sched.num_instructions = 1;
   inst->alu_complement = 0;

   if (dst->File == TGSI_FILE_OUTPUT) {
      inst->dw.enable = true;
      inst->dw.index = 1 + dst->Index;
      inst->dw.stencil_write = false;
      inst->dw.src_regs = FP_DW_REGS_R2_R3;
      fp_note_dw_exec(fp);
   }

   list_addtail(&mfu0->link, &fp->mfu_instructions);
   list_addtail(&mfu1->link, &fp->mfu_instructions);
   list_addtail(&alu->link, &fp->alu_instructions);
   list_addtail(&inst->link, &fp->fp_instructions);
   return true;
}

static bool
fp_emit_alu(struct grate_fp_shader *fp,
            struct fp_lowering_state *lowering,
            const struct tgsi_full_instruction *tgsi_inst,
            bool force_mov)
{
   const struct tgsi_dst_register *dst = &tgsi_inst->Dst[0].Register;
   bool saturate = tgsi_inst->Instruction.Saturate != 0;
   unsigned components[4];
   unsigned num_components = 0;

   for (unsigned c = 0; c < 4; ++c) {
      if (dst->WriteMask & (1u << c))
         components[num_components++] = c;
   }

   if (num_components == 0)
      return true;

   if (dst->File == TGSI_FILE_TEMPORARY && !force_mov) {
      const struct tgsi_src_register *src0 =
         tgsi_inst->Instruction.NumSrcRegs == 1 ?
         &tgsi_inst->Src[0].Register : NULL;

      /*
       * NIR-to-TGSI commonly emits identity self-MOVs after TEX.  Emitting
       * those as separate PSEQ EXECs needlessly recirculates fixed10 texels
       * through fragment GPRs.  Preserve aliases when the write is exactly
       * TEMP[n].component <- TEMP[n].component.
       */
      bool identity_self_mov =
         tgsi_inst->Instruction.Opcode == TGSI_OPCODE_MOV &&
         !saturate && src0 && !src0->Negate && !src0->Absolute &&
         src0->File == TGSI_FILE_TEMPORARY &&
         src0->Index == dst->Index;

      if (identity_self_mov) {
         for (unsigned i = 0; i < num_components; ++i) {
            unsigned component = components[i];
            if (fp_src_swizzle(src0, component) != component) {
               identity_self_mov = false;
               break;
            }
         }
      }

      if (identity_self_mov)
         return true;

      /* Any real write kills older scalar aliases and pending TEX components. */
      for (unsigned i = 0; i < num_components; ++i) {
         unsigned component = components[i];
         unsigned scalar = dst->Index * 4 + component;
         if (scalar >= FP_GPR_COUNT)
            return fp_fail(fp,
                           "fragment temporary TEMP[%u].%u exceeds %u FP20 GPR scalars",
                           dst->Index, component, FP_GPR_COUNT);
         lowering->temp_alias[scalar].valid = false;

         if (dst->Index < FP_GPR_COUNT / 4) {
            struct fp_pending_tex *pending =
               &lowering->pending_tex[dst->Index];
            pending->component_mask &= ~(1u << component);
            if (!pending->component_mask)
               pending->valid = false;
         }
      }

      const bool aliasable_mov =
         tgsi_inst->Instruction.Opcode == TGSI_OPCODE_MOV &&
         !saturate && src0 && !src0->Negate && !src0->Absolute &&
         (src0->File == TGSI_FILE_INPUT ||
          src0->File == TGSI_FILE_CONSTANT ||
          src0->File == TGSI_FILE_IMMEDIATE);

      if (aliasable_mov) {
         for (unsigned i = 0; i < num_components; ++i) {
            unsigned component = components[i];
            unsigned scalar = dst->Index * 4 + component;
            lowering->temp_alias[scalar].valid = true;
            lowering->temp_alias[scalar].src = *src0;
            lowering->temp_alias[scalar].component = component;
         }
         return true;
      }
   }

   /*
    * ALU3 is the immediate payload when any non-0/1 immediate is used. Keep
    * each such scalar in its own packet so three embedded constants are always
    * enough even for MAD. Normal wlroots uniform/texture arithmetic keeps all
    * four ALUs available and remains one packet.
    */
   unsigned group_limit = fp_instruction_uses_embedded(fp, tgsi_inst) ? 1 : 4;
   for (unsigned i = 0; i < num_components; ++i) {
      unsigned a, b, swz;
      if (fp_find_two_input_row_conflict(tgsi_inst, components[i],
                                         &a, &b, &swz)) {
         group_limit = 1;
         break;
      }
   }

   for (unsigned base = 0; base < num_components; base += group_limit) {
      unsigned group = num_components - base;
      if (group > group_limit)
         group = group_limit;

      if (list_length(&fp->fp_instructions) >= 63 ||
          list_length(&fp->alu_instructions) >= 63)
         return fp_fail(fp, "fragment program exceeds 63 PSEQ/ALU packet entries");

      if (group == 1) {
         unsigned first_src, second_src, swizzle;
         if (fp_find_two_input_row_conflict(tgsi_inst, components[base],
                                            &first_src, &second_src, &swizzle)) {
            if (!fp_emit_two_input_row_conflict(fp, tgsi_inst,
                                                components[base],
                                                first_src, second_src,
                                                swizzle, saturate))
               return false;
            continue;
         }
      }

      struct fp_instr *inst = CALLOC_STRUCT(fp_instr);
      struct fp_alu_instr_packet *alu = CALLOC_STRUCT(fp_alu_instr_packet);
      struct fp_mfu_instr *mfu = CALLOC_STRUCT(fp_mfu_instr);
      if (!inst || !alu || !mfu) {
         FREE(inst);
         FREE(alu);
         FREE(mfu);
         return fp_fail(fp, "out of memory lowering fragment ALU");
      }

      list_inithead(&inst->link);
      list_inithead(&alu->link);
      list_inithead(&mfu->link);

      int varying_rows[4] = { -1, -1, -1, -1 };
      bool uses_mfu = false;
      int tex_temp_index = -1;

      for (unsigned slot = 0; slot < group; ++slot) {
         unsigned component = components[base + slot];
         struct fp_alu_dst_operand d;
         struct fp_alu_src_operand src[3] = {0};

         if (!fp_dst_component(fp, dst, component, saturate, &d))
            goto fail_packet;

         for (unsigned s = 0; s < tgsi_inst->Instruction.NumSrcRegs; ++s) {
            if (s >= 3) {
               fp_fail(fp, "fragment opcode %u has more than three ALU sources",
                       tgsi_inst->Instruction.Opcode);
               goto fail_packet;
            }

            if (!fp_src_component(fp, lowering, alu, mfu, varying_rows,
                                  &tgsi_inst->Src[s].Register,
                                  component, &src[s], &uses_mfu,
                                  &tex_temp_index))
               goto fail_packet;
         }

         switch (tgsi_inst->Instruction.Opcode) {
         case TGSI_OPCODE_MOV:
            alu->slots[slot] = fp_make_mov(d, src[0]);
            break;
         case TGSI_OPCODE_ADD:
            alu->slots[slot] = fp_make_add(d, src[0], src[1]);
            break;
         case TGSI_OPCODE_MUL:
            alu->slots[slot] = fp_make_mul(d, src[0], src[1]);
            break;
         case TGSI_OPCODE_MAD:
            alu->slots[slot] = fp_make_mad(d, src[0], src[1], src[2]);
            break;
         case TGSI_OPCODE_MIN:
            alu->slots[slot] = fp_make_min(d, src[0], src[1]);
            break;
         case TGSI_OPCODE_MAX:
            alu->slots[slot] = fp_make_max(d, src[0], src[1]);
            break;
         default:
            fp_fail(fp, "unsupported fragment TGSI opcode %u",
                    tgsi_inst->Instruction.Opcode);
            goto fail_packet;
         }
      }

      if (alu->uses_embedded_constants && group > 3) {
         fp_fail(fp, "embedded fragment constants consume ALU3");
         goto fail_packet;
      }

      inst->alu_sched.num_instructions = 1;
      inst->alu_sched.address = list_length(&fp->alu_instructions);
      inst->alu_complement = alu->complement;

      if (tex_temp_index >= 0) {
         const struct fp_pending_tex *pending =
            &lowering->pending_tex[tex_temp_index];

         if (!pending->valid ||
             pending->coord.File != TGSI_FILE_INPUT ||
             pending->sampler_index >= 16) {
            fp_fail(fp, "invalid deferred fragment texture alias");
            goto fail_packet;
         }

         for (unsigned coord_component = 0; coord_component < 2;
              ++coord_component) {
            if (varying_rows[coord_component] >= 0 &&
                varying_rows[coord_component] != (int)pending->coord.Index) {
               fp_fail(fp,
                       "deferred TEX coordinate conflicts with ALU varying row");
               goto fail_packet;
            }

            varying_rows[coord_component] = pending->coord.Index;
            mfu->var[coord_component].op = FP_VAR_OP_FP20;
            mfu->var[coord_component].tram_row = pending->coord.Index;
         }

         if ((int)pending->coord.Index + 1 > fp->info.max_tram_row)
            fp->info.max_tram_row = pending->coord.Index + 1;

         uses_mfu = true;
         inst->tex.enable = true;
         inst->tex.sampler_index = pending->sampler_index;
         inst->tex.src_regs_select = 0;
         /*
          * Fused TEX+ALU must keep the sample out of r2/r3 because output
          * ALU destinations use those registers.  r0/r1 are read directly by
          * fp_src_texel(..., 0) in the same EXEC.
          */
         inst->tex.sample_dst_regs_select = 0;
      }

      if (uses_mfu) {
         if (list_length(&fp->mfu_instructions) >= 63) {
            fp_fail(fp, "fragment program exceeds 63 MFU instructions");
            goto fail_packet;
         }
         inst->mfu_sched.num_instructions = 1;
         inst->mfu_sched.address = list_length(&fp->mfu_instructions);
         list_addtail(&mfu->link, &fp->mfu_instructions);
      } else {
         FREE(mfu);
      }

      bool final_group = base + group == num_components;
      if (dst->File == TGSI_FILE_OUTPUT && final_group) {
         inst->dw.enable = true;
         inst->dw.index = 1 + dst->Index;
         inst->dw.stencil_write = false;
         inst->dw.src_regs = FP_DW_REGS_R2_R3;
         fp_note_dw_exec(fp);
      }

      list_addtail(&alu->link, &fp->alu_instructions);
      list_addtail(&inst->link, &fp->fp_instructions);
      continue;

fail_packet:
      FREE(mfu);
      FREE(alu);
      FREE(inst);
      return false;
   }

   if (force_mov && dst->File == TGSI_FILE_TEMPORARY) {
      for (unsigned c = 0; c < 4; ++c) {
         if (!(dst->WriteMask & (1u << c)))
            continue;
         unsigned scalar = dst->Index * 4 + c;
         lowering->temp_alias[scalar].valid = false;
         struct fp_pending_tex *pending = &lowering->pending_tex[dst->Index];
         pending->component_mask &= ~(1u << c);
         if (!pending->component_mask)
            pending->valid = false;
      }
   }
   return true;
}

/* SFU instructions read physical scalar GPRs, not row/uniform operands. */
static bool
fp_sfu_source_gpr(struct grate_fp_shader *fp,
                  struct fp_lowering_state *lowering,
                  const struct tgsi_full_instruction *tgsi_inst,
                  unsigned *gpr)
{
   const struct tgsi_src_register *src = &tgsi_inst->Src[0].Register;
   const struct tgsi_dst_register *dst = &tgsi_inst->Dst[0].Register;
   unsigned swizzle = fp_src_swizzle(src, 0);
   if (swizzle >= 4)
      return fp_fail(fp, "invalid fragment SFU source swizzle %u", swizzle);

   if (src->File == TGSI_FILE_TEMPORARY) {
      unsigned scalar = src->Index * 4 + swizzle;
      if (scalar >= FP_GPR_COUNT)
         return fp_fail(fp, "fragment SFU TEMP[%u].%u exceeds GPR range",
                        src->Index, swizzle);
      bool pending = src->Index < FP_GPR_COUNT / 4 &&
                     lowering->pending_tex[src->Index].valid &&
                     (lowering->pending_tex[src->Index].component_mask &
                      (1u << swizzle));
      if (!src->Negate && !src->Absolute &&
          !lowering->temp_alias[scalar].valid && !pending) {
         *gpr = scalar;
         return true;
      }
   }

   /*
    * A writable TEMP scalar is safe staging storage (it is overwritten by
    * this opcode). For OUTPUT, only use an undeclared TEMP register: silently
    * taking a live GPR would corrupt later instructions.
    */
   unsigned scratch = FP_GPR_COUNT;
   if (dst->File == TGSI_FILE_TEMPORARY) {
      for (unsigned c = 0; c < 4; ++c)
         if (dst->WriteMask & (1u << c)) {
            scratch = dst->Index * 4 + c;
            break;
         }
   } else if (dst->File == TGSI_FILE_OUTPUT) {
      scratch = lowering->declared_temps * 4;
   }
   if (scratch >= FP_GPR_COUNT)
      return fp_fail(fp, "fragment SFU needs a free scalar staging GPR");

   /* Force a genuine MOV EXEC, bypassing the normal TEMP alias fast path. */
   struct tgsi_full_instruction mov = *tgsi_inst;
   mov.Instruction.Opcode = TGSI_OPCODE_MOV;
   mov.Instruction.NumSrcRegs = 1;
   mov.Instruction.Saturate = 0;
   mov.Dst[0].Register.File = TGSI_FILE_TEMPORARY;
   mov.Dst[0].Register.Index = scratch / 4;
   mov.Dst[0].Register.WriteMask = 1u << (scratch % 4);
   /* Scalar SFU instructions always sample the TGSI source's X swizzle. */
   mov.Src[0].Register.SwizzleX = swizzle;
   mov.Src[0].Register.SwizzleY = swizzle;
   mov.Src[0].Register.SwizzleZ = swizzle;
   mov.Src[0].Register.SwizzleW = swizzle;
   if (!fp_emit_alu(fp, lowering, &mov, true))
      return false;
   *gpr = scratch;
   return true;
}

static bool
fp_emit_sfu(struct grate_fp_shader *fp,
            struct fp_lowering_state *lowering,
            const struct tgsi_full_instruction *tgsi_inst,
            enum fp_sfu_op pre_op, enum fp_sfu_op result_op)
{
   const struct tgsi_dst_register *dst = &tgsi_inst->Dst[0].Register;
   const bool saturate = tgsi_inst->Instruction.Saturate != 0;
   const unsigned steps = pre_op == FP_SFU_OP_NOP ? 1 : 2;
   struct fp_instr *exec[2] = {NULL, NULL};
   struct fp_mfu_instr *mfu[2] = {NULL, NULL};
   struct fp_alu_instr_packet *alu[2] = {NULL, NULL};
   unsigned source_gpr;

   if (!dst->WriteMask)
      return true;
   if (tgsi_inst->Instruction.NumSrcRegs != 1)
      return fp_fail(fp, "fragment SFU expects exactly one source");
   if (!fp_sfu_source_gpr(fp, lowering, tgsi_inst, &source_gpr))
      return false;
   if (list_length(&fp->fp_instructions) + steps > 63 ||
       list_length(&fp->mfu_instructions) + steps > 63 ||
       list_length(&fp->alu_instructions) + steps > 63)
      return fp_fail(fp, "fragment SFU exceeds 63-slot scheduling limits");

   const unsigned mfu_base = list_length(&fp->mfu_instructions);
   const unsigned alu_base = list_length(&fp->alu_instructions);
   const unsigned last_exec = list_length(&fp->fp_instructions) + steps;
   for (unsigned i = 0; i < steps; ++i) {
      exec[i] = CALLOC_STRUCT(fp_instr);
      mfu[i] = CALLOC_STRUCT(fp_mfu_instr);
      alu[i] = CALLOC_STRUCT(fp_alu_instr_packet);
      if (!exec[i] || !mfu[i] || !alu[i]) {
         fp_fail(fp, "out of memory lowering fragment SFU");
         goto fail;
      }
      list_inithead(&exec[i]->link);
      list_inithead(&mfu[i]->link);
      list_inithead(&alu[i]->link);
      mfu[i]->sfu.op = (i == 0 && steps == 2) ? pre_op : result_op;
      mfu[i]->sfu.reg = i == 0 ? source_gpr : 0;
      mfu[i]->mul[0].dst = FP_MFU_MUL_DST_ROW_REG_0;
      mfu[i]->mul[0].src[0] = FP_MFU_MUL_SRC_SFU_RESULT;
      mfu[i]->mul[0].src[1] = FP_MFU_MUL_SRC_CONST_1;
      exec[i]->mfu_sched.address = mfu_base + i;
      exec[i]->mfu_sched.num_instructions = 1;
      exec[i]->alu_sched.address = alu_base + i;
      exec[i]->alu_sched.num_instructions = 1;
   }

   /* The PRE* stage emits a no-write ALU packet; the final stage fans out
    * one scalar SFU result to all written components in one EXEC. This also
    * prevents in-place TEMP writes from clobbering the source mid-operation.
    */
   unsigned slot = 0;
   for (unsigned c = 0; c < 4; ++c) {
      if (!(dst->WriteMask & (1u << c)))
         continue;
      struct fp_alu_dst_operand d;
      if (!fp_dst_component(fp, dst, c, saturate, &d))
         goto fail;
      alu[steps - 1]->slots[slot++] = fp_make_mov(d, fp_src_row(0));
   }
   if (dst->File == TGSI_FILE_OUTPUT) {
      exec[steps - 1]->dw.enable = true;
      exec[steps - 1]->dw.index = 1 + dst->Index;
      exec[steps - 1]->dw.src_regs = FP_DW_REGS_R2_R3;
      if (last_exec > fp->info.pseq_to_dw_exec_nb)
         fp->info.pseq_to_dw_exec_nb = last_exec;
   }

   for (unsigned i = 0; i < steps; ++i) {
      list_addtail(&mfu[i]->link, &fp->mfu_instructions);
      list_addtail(&alu[i]->link, &fp->alu_instructions);
      list_addtail(&exec[i]->link, &fp->fp_instructions);
   }
   if (dst->File == TGSI_FILE_TEMPORARY) {
      for (unsigned c = 0; c < 4; ++c) {
         if (!(dst->WriteMask & (1u << c)))
            continue;
         unsigned scalar = dst->Index * 4 + c;
         lowering->temp_alias[scalar].valid = false;
         struct fp_pending_tex *pending = &lowering->pending_tex[dst->Index];
         pending->component_mask &= ~(1u << c);
         if (!pending->component_mask)
            pending->valid = false;
      }
   }
   return true;

fail:
   for (unsigned i = 0; i < steps; ++i) {
      FREE(exec[i]);
      FREE(mfu[i]);
      FREE(alu[i]);
   }
   return false;
}

static bool
fp_emit_sfu_direct(struct grate_fp_shader *fp,
                   struct fp_lowering_state *lowering,
                   const struct tgsi_full_instruction *tgsi_inst,
                   enum fp_sfu_op op)
{
   return fp_emit_sfu(fp, lowering, tgsi_inst, FP_SFU_OP_NOP, op);
}

static bool
fp_emit_sfu_twostage(struct grate_fp_shader *fp,
                     struct fp_lowering_state *lowering,
                     const struct tgsi_full_instruction *tgsi_inst,
                     enum fp_sfu_op pre_op, enum fp_sfu_op op)
{
   return fp_emit_sfu(fp, lowering, tgsi_inst, pre_op, op);
}


static bool
fp_emit_tex(struct grate_fp_shader *fp,
            struct fp_lowering_state *lowering,
            const struct tgsi_full_instruction *tgsi)
{
   const struct tgsi_dst_register *dst = &tgsi->Dst[0].Register;
   const struct tgsi_src_register *coord = &tgsi->Src[0].Register;
   const struct tgsi_src_register *sampler = &tgsi->Src[1].Register;
   bool saturate = tgsi->Instruction.Saturate != 0;

   if (!tgsi->Instruction.Texture || tgsi->Texture.Texture != TGSI_TEXTURE_2D)
      return fp_fail(fp, "only TGSI_TEXTURE_2D is supported");
   if (coord->File != TGSI_FILE_INPUT)
      return fp_fail(fp, "texture coordinates must come from a varying input");
   if (sampler->File != TGSI_FILE_SAMPLER || sampler->Index >= 16)
      return fp_fail(fp, "texture sampler must be a direct sampler index < 16");
   if (coord->Index >= FP_ROW_REG_COUNT)
      return fp_fail(fp, "texture coordinate INPUT[%u] exceeds TRAM rows",
                     coord->Index);

   /*
    * Keep TEX-to-TEMP virtual until an ALU instruction consumes it.  Tegra20
    * texture results are reliable inside their producing EXEC, while live
    * qualification shows fixed10 texels do not reliably survive GPR
    * recirculation across later PSEQ EXECs.  Re-sampling in the consumer EXEC
    * is semantically equivalent for immutable shader inputs and avoids that
    * lifetime boundary.
    */
   if (dst->File == TGSI_FILE_TEMPORARY && !saturate) {
      if (dst->Index >= FP_GPR_COUNT / 4)
         return fp_fail(fp,
                        "fragment TEX TEMP[%u] exceeds temporary range",
                        dst->Index);

      struct fp_pending_tex *pending = &lowering->pending_tex[dst->Index];
      pending->valid = true;
      pending->component_mask = dst->WriteMask;
      pending->coord = *coord;
      pending->sampler_index = sampler->Index;

      for (unsigned component = 0; component < 4; ++component) {
         if (!(dst->WriteMask & (1u << component)))
            continue;
         lowering->temp_alias[dst->Index * 4 + component].valid = false;
      }

      return true;
   }

   if (list_length(&fp->fp_instructions) >= 63 ||
       list_length(&fp->mfu_instructions) >= 63 ||
       list_length(&fp->alu_instructions) >= 63)
      return fp_fail(fp, "fragment TEX exceeds 63-slot scheduling limits");

   const bool direct_output =
      dst->File == TGSI_FILE_OUTPUT &&
      dst->WriteMask == TGSI_WRITEMASK_XYZW &&
      !saturate;
   const bool output_via_alu =
      dst->File == TGSI_FILE_OUTPUT && !direct_output;

   struct fp_instr *inst = CALLOC_STRUCT(fp_instr);
   struct fp_mfu_instr *mfu = CALLOC_STRUCT(fp_mfu_instr);
   struct fp_alu_instr_packet *alu =
      direct_output ? NULL : CALLOC_STRUCT(fp_alu_instr_packet);
   if (!inst || !mfu || (!direct_output && !alu)) {
      FREE(inst);
      FREE(mfu);
      FREE(alu);
      return fp_fail(fp, "out of memory lowering fragment TEX");
   }

   list_inithead(&inst->link);
   list_inithead(&mfu->link);
   if (alu)
      list_inithead(&alu->link);

   mfu->var[0].op = FP_VAR_OP_FP20;
   mfu->var[0].tram_row = coord->Index;
   mfu->var[1].op = FP_VAR_OP_FP20;
   mfu->var[1].tram_row = coord->Index;
   if ((int)coord->Index + 1 > fp->info.max_tram_row)
      fp->info.max_tram_row = coord->Index + 1;

   inst->mfu_sched.num_instructions = 1;
   inst->mfu_sched.address = list_length(&fp->mfu_instructions);

   inst->tex.enable = true;
   inst->tex.sampler_index = sampler->Index;
   inst->tex.src_regs_select = 0;
   inst->tex.sample_dst_regs_select = output_via_alu ? 0 : 1;

   if (alu) {
      const unsigned texel_base_reg = output_via_alu ? 0 : 2;
      unsigned slot = 0;

      for (unsigned component = 0; component < 4; ++component) {
         if (!(dst->WriteMask & (1u << component)))
            continue;

         struct fp_alu_dst_operand d;
         if (!fp_dst_component(fp, dst, component, saturate, &d))
            goto fail;

         alu->slots[slot++] =
            fp_make_mov(d, fp_src_texel(component, texel_base_reg));
      }

      inst->alu_sched.num_instructions = 1;
      inst->alu_sched.address = list_length(&fp->alu_instructions);
      inst->alu_complement = alu->complement;
   }

   if (dst->File == TGSI_FILE_OUTPUT) {
      inst->dw.enable = true;
      inst->dw.index = 1 + dst->Index;
      inst->dw.stencil_write = false;
      inst->dw.src_regs = FP_DW_REGS_R2_R3;
      fp_note_dw_exec(fp);
   }

   list_addtail(&mfu->link, &fp->mfu_instructions);
   if (alu)
      list_addtail(&alu->link, &fp->alu_instructions);
   list_addtail(&inst->link, &fp->fp_instructions);
   return true;

fail:
   FREE(mfu);
   FREE(alu);
   FREE(inst);
   return false;
}

#define LINK_SRC(export_index, tram_row) \
   (((export_index) << 3) | ((tram_row) << 9))
#define LINK_DST(index, comp, type) (((comp) | (type) << 2) << ((index) * 4))
#define LINK_DST_FP20 3

static bool
fp_emit_input(struct grate_fp_shader *fp,
              const struct tgsi_full_declaration *decl)
{
   for (unsigned input = decl->Range.First; input <= decl->Range.Last; ++input) {
      if (fp->info.num_inputs >= 16)
         return fp_fail(fp, "fragment shader declares more than 16 inputs");
      if (input >= 15)
         return fp_fail(fp,
                        "fragment INPUT[%u] has no matching vertex varying export",
                        input);

      /* Vertex export 0 is position; fragment varying N consumes export N+1. */
      uint32_t src = LINK_SRC(input + 1, input);
      uint32_t dst = 0;
      for (int i = 0; i < 4; ++i)
         dst |= LINK_DST(i, i, LINK_DST_FP20);

      fp->info.inputs[fp->info.num_inputs].src = src;
      fp->info.inputs[fp->info.num_inputs].dst = dst;

      if (decl->Declaration.Semantic == TGSI_SEMANTIC_COLOR)
         fp->info.color_input = fp->info.num_inputs;

      fp->info.num_inputs++;

      if (input == decl->Range.Last)
         break;
   }

   return true;
}

static bool
fp_emit_declaration(struct grate_fp_shader *fp,
                    const struct tgsi_full_declaration *decl)
{
   if (decl->Declaration.File == TGSI_FILE_INPUT)
      return fp_emit_input(fp, decl);

   return true;
}

static bool
fp_emit_immediate(struct grate_fp_shader *fp,
                  const struct tgsi_full_immediate *imm)
{
   if (fp->num_immediates >= 256)
      return fp_fail(fp, "fragment shader declares more than 256 TGSI immediates");

   for (unsigned i = 0; i < 4; ++i)
      fp->immediates[fp->num_immediates][i] = imm->u[i].Float;

   fp->num_immediates++;
   return true;
}

void
grate_tgsi_to_fp(struct grate_fp_shader *fp, struct tgsi_parse_context *tgsi)
{
   memset(fp, 0, sizeof(*fp));
   list_inithead(&fp->fp_instructions);
   list_inithead(&fp->alu_instructions);
   list_inithead(&fp->mfu_instructions);

   fp->info.color_input = -1;
   fp->info.max_tram_row = 1;
   struct fp_lowering_state lowering = {0};

   while (!tgsi_parse_end_of_tokens(tgsi) && !fp->failed) {
      tgsi_parse_token(tgsi);
      switch (tgsi->FullToken.Token.Type) {
      case TGSI_TOKEN_TYPE_DECLARATION:
         if (tgsi->FullToken.FullDeclaration.Declaration.File == TGSI_FILE_TEMPORARY) {
            unsigned count = tgsi->FullToken.FullDeclaration.Range.Last + 1;
            if (count > lowering.declared_temps)
               lowering.declared_temps = count;
         }
         fp_emit_declaration(fp, &tgsi->FullToken.FullDeclaration);
         break;

      case TGSI_TOKEN_TYPE_IMMEDIATE:
         fp_emit_immediate(fp, &tgsi->FullToken.FullImmediate);
         break;

      case TGSI_TOKEN_TYPE_INSTRUCTION:
         if (tgsi->FullToken.FullInstruction.Instruction.Opcode == TGSI_OPCODE_TEX)
            fp_emit_tex(fp, &lowering, &tgsi->FullToken.FullInstruction);
         else if (tgsi->FullToken.FullInstruction.Instruction.Opcode != TGSI_OPCODE_END) {
            const struct tgsi_full_instruction *inst = &tgsi->FullToken.FullInstruction;
            switch (inst->Instruction.Opcode) {
            case TGSI_OPCODE_RCP:
               fp_emit_sfu_direct(fp, &lowering, inst, FP_SFU_OP_RCP);
               break;
            case TGSI_OPCODE_RSQ:
               fp_emit_sfu_direct(fp, &lowering, inst, FP_SFU_OP_RSQ);
               break;
            case TGSI_OPCODE_LG2:
               fp_emit_sfu_direct(fp, &lowering, inst, FP_SFU_OP_LG2);
               break;
            case TGSI_OPCODE_SQRT:
               fp_emit_sfu_direct(fp, &lowering, inst, FP_SFU_OP_SQRT);
               break;
            case TGSI_OPCODE_EX2:
               fp_emit_sfu_twostage(fp, &lowering, inst,
                                    FP_SFU_OP_PREEX2, FP_SFU_OP_EX2);
               break;
            case TGSI_OPCODE_SIN:
               fp_emit_sfu_twostage(fp, &lowering, inst,
                                    FP_SFU_OP_PRESIN, FP_SFU_OP_SIN);
               break;
            case TGSI_OPCODE_COS:
               fp_emit_sfu_twostage(fp, &lowering, inst,
                                    FP_SFU_OP_PRECOS, FP_SFU_OP_COS);
               break;
            default:
               fp_emit_alu(fp, &lowering, inst, false);
               break;
            }
         }
         break;
      }
   }

   if (fp->failed)
      return;

   /*
    * Each separately scheduled MFU interpolation sequence needs its own
    * barycentric setup.  r4 is only guaranteed as the fragment-w input to
    * the first instruction of an MFU sequence, so installing rcp/mul0/mul1
    * only on the first MFU in the whole shader corrupts later scalar-split
    * varying reads.
    */
   list_for_each_entry(struct fp_mfu_instr, mfu,
                       &fp->mfu_instructions, link) {
      bool interpolates = false;

      for (unsigned i = 0; i < 4; ++i) {
         if (mfu->var[i].op != FP_VAR_OP_NOP) {
            interpolates = true;
            break;
         }
      }

      if (!interpolates)
         continue;

      /*
       * A preconfigured MFU multiply belongs to an already-started MFU
       * sequence (currently the two-varying row-preservation path).  Reuse
       * the barycentric weights established by the preceding MFU instead of
       * overwriting its row-copy multiply with another rcp/bar setup.
       */
      if (mfu->mul[0].dst != 0 || mfu->mul[1].dst != 0 ||
          mfu->sfu.op != FP_SFU_OP_NOP)
         continue;

      mfu->sfu.op = FP_SFU_OP_RCP;
      mfu->sfu.reg = 4;
      mfu->mul[0].dst = FP_MFU_MUL_DST_BARYCENTRIC_WEIGHT;
      mfu->mul[0].src[0] = FP_MFU_MUL_SRC_SFU_RESULT;
      mfu->mul[0].src[1] = FP_MFU_MUL_SRC_BARYCENTRIC_COEF_0;

      mfu->mul[1].dst = FP_MFU_MUL_DST_BARYCENTRIC_WEIGHT;
      mfu->mul[1].src[0] = FP_MFU_MUL_SRC_SFU_RESULT;
      mfu->mul[1].src[1] = FP_MFU_MUL_SRC_BARYCENTRIC_COEF_1;
   }
}

static struct fp_alu_src_operand
fp_src_fixed10(unsigned reg, bool high)
{
   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = reg,
      .datatype = FP_DATATYPE_FIXED10,
      .sub_reg_select_high = high,
   };
}

static struct fp_alu_src_operand
fp_src_alu_result(unsigned slot)
{
   return (struct fp_alu_src_operand) {
      .enable = true,
      .index = FP_ALU_RESULT_BASE + slot,
      .datatype = FP_DATATYPE_FIXED10,
   };
}

static struct fp_alu_dst_operand
fp_dst_fixed10(unsigned reg, bool high, bool saturate)
{
   return (struct fp_alu_dst_operand) {
      .index = reg,
      .write_low_sub_reg = !high,
      .write_high_sub_reg = high,
      .saturate = saturate,
   };
}

bool
grate_fp_enable_premultiplied_src_over(struct grate_fp_shader *fp)
{
   struct fp_instr *save = NULL, *blend = NULL;
   struct fp_alu_instr_packet *save_alu = NULL;
   struct fp_alu_instr_packet *blend_alu = NULL;
   int rt = -1;

   if (fp->failed)
      return false;

   /*
    * Tegra20 has no reverse-engineered fixed-function blend register.
    * OpenTegra implements Porter-Duff OVER with a fragment destination fetch
    * (PSEQ 0x0081000a), shader arithmetic and an ordinary DW store.  Preserve
    * that hardware contract for Gallium's premultiplied source-over state.
    */
   list_for_each_entry(struct fp_instr, inst, &fp->fp_instructions, link) {
      if (!inst->dw.enable)
         continue;
      if (rt >= 0 && rt != inst->dw.index)
         return fp_fail(fp, "source-over variant supports one render target");
      rt = inst->dw.index;
      inst->dw.enable = false;
   }

   if (rt < 0)
      return fp_fail(fp, "source-over variant has no color DW");

   if (list_length(&fp->fp_instructions) > 61 ||
       list_length(&fp->alu_instructions) > 60)
      return fp_fail(fp, "source-over variant exceeds fragment scheduling limits");

   save = CALLOC_STRUCT(fp_instr);
   blend = CALLOC_STRUCT(fp_instr);
   save_alu = CALLOC_STRUCT(fp_alu_instr_packet);
   blend_alu = CALLOC_STRUCT(fp_alu_instr_packet);
   if (!save || !blend || !save_alu || !blend_alu)
      goto oom;

   list_inithead(&save->link);
   list_inithead(&blend->link);
   list_inithead(&save_alu->link);
   list_inithead(&blend_alu->link);

   /*
    * The normal compiler leaves the shader result in r2/r3 as BGRA fixed10.
    * Save it in r0/r1 before destination fetch overwrites r2/r3.
    */
   for (unsigned c = 0; c < 4; ++c) {
      unsigned src_reg = 2 + c / 2;
      bool high = c & 1;
      unsigned dst_reg = c / 2;
      save_alu->slots[c] =
         fp_make_mov(fp_dst_fixed10(dst_reg, high, false),
                     fp_src_fixed10(src_reg, high));
   }
   save->alu_sched.address = list_length(&fp->alu_instructions);
   save->alu_sched.num_instructions = 1;

   /*
    * Destination fetch puts dst BGRA in r2/r3.  Source alpha is already
    * saved in r1.h.  Tegra's fx10 source modifier can decrement by 1, so
    *
    *   (-dst) * (src.a - 1) + src
    *
    * is exactly premultiplied Porter-Duff OVER:
    *
    *   dst * (1 - src.a) + src
    *
    * This fits in one MAD packet and avoids carrying ALU result registers
    * across consecutively scheduled ALU packets.
    */
   struct fp_alu_src_operand src_factor = fp_src_fixed10(1, true);
   src_factor.minus_one = true;
   for (unsigned c = 0; c < 4; ++c) {
      /*
       * Live T20 destination-fetch qualification shows r2/r3 already carry
       * semantic RGBA here.  Do not apply an additional R/B swap.
       */
      unsigned dst_reg = 2 + c / 2;
      bool dst_high = c & 1;
      unsigned out_reg = c / 2;
      bool high = c & 1;

      struct fp_alu_src_operand dst =
         fp_src_fixed10(dst_reg, dst_high);
      dst.negate = true;

      blend_alu->slots[c] = (struct fp_alu_instr) {
         .op = FP_ALU_OP_MAD,
         .dst = fp_dst_fixed10(out_reg, high, true),
         .src = {
            dst,
            src_factor,
            fp_src_fixed10(out_reg, high),
            fp_src_disabled_one(),
         },
      };
   }

   blend->pseq = 0x0081000a;
   blend->alu_sched.address = list_length(&fp->alu_instructions) + 1;
   blend->alu_sched.num_instructions = 1;
   blend->dw.enable = true;
   blend->dw.index = rt;
   blend->dw.src_regs = FP_DW_REGS_R0_R1;

   list_addtail(&save_alu->link, &fp->alu_instructions);
   list_addtail(&blend_alu->link, &fp->alu_instructions);
   list_addtail(&save->link, &fp->fp_instructions);
   list_addtail(&blend->link, &fp->fp_instructions);

   fp->info.pseq_to_dw_exec_nb = list_length(&fp->fp_instructions);
   return true;

oom:
   FREE(save);
   FREE(blend);
   FREE(save_alu);
   FREE(blend_alu);
   return fp_fail(fp, "out of memory creating source-over variant");
}
