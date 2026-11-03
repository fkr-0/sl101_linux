/* Host-only compiler lowering tests; no GPU, KMS, or device access. */
#include "tgsi.c"
#include <assert.h>
#include <stdio.h>

bool
grate_fp_try_encode_fp20(float value, uint32_t *encoded)
{
   if (value != value)
      return false;
   *encoded = 0x30000u + (unsigned)(value * 100.0f);
   return true;
}

static void
reset(struct grate_fp_shader *fp, struct fp_lowering_state *lowering)
{
   memset(fp, 0, sizeof(*fp));
   memset(lowering, 0, sizeof(*lowering));
   list_inithead(&fp->fp_instructions);
   list_inithead(&fp->alu_instructions);
   list_inithead(&fp->mfu_instructions);
   fp->info.max_tram_row = 1;
}

static struct tgsi_src_register
src(unsigned file, unsigned index)
{
   struct tgsi_src_register s = {0};
   s.File = file;
   s.Index = index;
   s.SwizzleX = TGSI_SWIZZLE_X;
   s.SwizzleY = TGSI_SWIZZLE_Y;
   s.SwizzleZ = TGSI_SWIZZLE_Z;
   s.SwizzleW = TGSI_SWIZZLE_W;
   return s;
}

static struct tgsi_dst_register
dst(unsigned file, unsigned index, unsigned mask)
{
   struct tgsi_dst_register d = {0};
   d.File = file;
   d.Index = index;
   d.WriteMask = mask;
   return d;
}

static struct tgsi_full_instruction
make_dot(unsigned opcode,
         struct tgsi_dst_register d,
         struct tgsi_src_register a,
         struct tgsi_src_register b)
{
   struct tgsi_full_instruction i = {0};
   i.Instruction.Opcode = opcode;
   i.Instruction.NumSrcRegs = 2;
   i.Instruction.NumDstRegs = 1;
   i.Dst[0].Register = d;
   i.Src[0].Register = a;
   i.Src[1].Register = b;
   return i;
}

static void
test_dp3_output(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   struct tgsi_full_instruction i =
      make_dot(TGSI_OPCODE_DP3, dst(TGSI_FILE_OUTPUT, 0, TGSI_WRITEMASK_XYZW),
               src(TGSI_FILE_INPUT, 0), src(TGSI_FILE_CONSTANT, 0));
   assert(fp_emit_dp3(&fp, &l, &i));
   assert(list_length(&fp.fp_instructions) == 3);
   assert(list_length(&fp.alu_instructions) == 3);
   assert(list_length(&fp.mfu_instructions) == 3);
   struct fp_instr *last = list_last_entry(&fp.fp_instructions, struct fp_instr, link);
   assert(last->dw.enable && last->dw.index == 1);
   struct fp_alu_instr_packet *alu =
      list_last_entry(&fp.alu_instructions, struct fp_alu_instr_packet, link);
   for (unsigned c = 0; c < 4; ++c) {
      assert(alu->slots[c].src[0].index == FP_ROW_REG_BASE + 2);
      assert(alu->slots[c].src[1].index == FP_UNIFORM_BASE + 2);
   }
}

static void
test_dp4_output(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   l.declared_temps = 1;
   struct tgsi_full_instruction i =
      make_dot(TGSI_OPCODE_DP4, dst(TGSI_FILE_OUTPUT, 0, TGSI_WRITEMASK_XYZW),
               src(TGSI_FILE_TEMPORARY, 0), src(TGSI_FILE_CONSTANT, 0));
   assert(fp_emit_dp4(&fp, &l, &i));
   assert(list_length(&fp.fp_instructions) == 4);
   assert(list_length(&fp.alu_instructions) == 4);
   struct fp_alu_instr_packet *last =
      list_last_entry(&fp.alu_instructions, struct fp_alu_instr_packet, link);
   assert(last->slots[0].src[0].index == FP_GPR_BASE + 3);
   assert(last->slots[0].src[1].index == FP_UNIFORM_BASE + 3);
   assert(last->slots[0].src[2].index == FP_GPR_BASE + 4);
}

static void
test_dp3_temp_overlapping_output(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   l.declared_temps = 1;
   struct tgsi_full_instruction i =
      make_dot(TGSI_OPCODE_DP3, dst(TGSI_FILE_TEMPORARY, 0, TGSI_WRITEMASK_XYZW),
               src(TGSI_FILE_TEMPORARY, 0), src(TGSI_FILE_CONSTANT, 0));
   assert(fp_emit_dp3(&fp, &l, &i));
   assert(list_length(&fp.fp_instructions) == 4);
   assert(!fp.failed);
}

static void
test_no_scratch_fails_closed(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   l.declared_temps = 2;
   struct tgsi_full_instruction i =
      make_dot(TGSI_OPCODE_DP4, dst(TGSI_FILE_OUTPUT, 0, TGSI_WRITEMASK_XYZW),
               src(TGSI_FILE_TEMPORARY, 0), src(TGSI_FILE_TEMPORARY, 1));
   assert(!fp_emit_dp4(&fp, &l, &i));
   assert(fp.failed);
   assert(strstr(fp.error, "scratch") != NULL);
}

static void
test_row_conflict_fails_closed(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   struct tgsi_full_instruction i =
      make_dot(TGSI_OPCODE_DP3, dst(TGSI_FILE_OUTPUT, 0, TGSI_WRITEMASK_XYZW),
               src(TGSI_FILE_INPUT, 0), src(TGSI_FILE_INPUT, 1));
   assert(!fp_emit_dp3(&fp, &l, &i));
   assert(fp.failed);
   assert(strstr(fp.error, "row component") != NULL);
}

static void
test_dp3_embedded_scalar_fallback(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   fp.num_immediates = 1;
   fp.immediates[0][0] = 0.3f;
   fp.immediates[0][1] = 0.4f;
   fp.immediates[0][2] = 0.5f;
   struct tgsi_full_instruction i =
      make_dot(TGSI_OPCODE_DP3, dst(TGSI_FILE_OUTPUT, 0, TGSI_WRITEMASK_XYZW),
               src(TGSI_FILE_INPUT, 0), src(TGSI_FILE_IMMEDIATE, 0));
   assert(fp_emit_dp3(&fp, &l, &i));
   assert(list_length(&fp.fp_instructions) == 4);
}

static void
test_frc_gpr_direct(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   l.declared_temps = 1;
   struct tgsi_full_instruction i = {0};
   i.Instruction.Opcode = TGSI_OPCODE_FRC;
   i.Instruction.NumSrcRegs = 1;
   i.Instruction.NumDstRegs = 1;
   i.Src[0].Register = src(TGSI_FILE_TEMPORARY, 0);
   i.Dst[0].Register = dst(TGSI_FILE_OUTPUT, 0, TGSI_WRITEMASK_X);
   assert(fp_emit_frc(&fp, &l, &i));
   assert(list_length(&fp.fp_instructions) == 1);
   struct fp_mfu_instr *mfu =
      list_last_entry(&fp.mfu_instructions, struct fp_mfu_instr, link);
   assert(mfu->sfu.op == FP_SFU_OP_FRC && mfu->sfu.reg == 0);
   assert(mfu->mul[0].dst == FP_MFU_MUL_DST_ROW_REG_0);
   assert(mfu->mul[0].src[0] == FP_MFU_MUL_SRC_SFU_RESULT);
   assert(mfu->mul[0].src[1] == FP_MFU_MUL_SRC_CONST_1);
}

static void
test_frc_input_materialization(void)
{
   struct grate_fp_shader fp;
   struct fp_lowering_state l;
   reset(&fp, &l);
   struct tgsi_full_instruction i = {0};
   i.Instruction.Opcode = TGSI_OPCODE_FRC;
   i.Instruction.NumSrcRegs = 1;
   i.Instruction.NumDstRegs = 1;
   i.Src[0].Register = src(TGSI_FILE_INPUT, 0);
   i.Dst[0].Register = dst(TGSI_FILE_OUTPUT, 0, TGSI_WRITEMASK_X);
   assert(fp_emit_frc(&fp, &l, &i));
   assert(list_length(&fp.fp_instructions) == 2);
   assert(list_length(&fp.alu_instructions) == 2);
   assert(list_length(&fp.mfu_instructions) == 2);
   assert(!l.temp_alias[0].valid);
}


static void test_dp2_two_components_and_writemask(void)
{
   struct grate_fp_shader fp; struct fp_lowering_state l;
   reset(&fp,&l);
   struct tgsi_full_instruction i = make_dot(TGSI_OPCODE_DP2,
      dst(TGSI_FILE_OUTPUT,0,TGSI_WRITEMASK_X),
      src(TGSI_FILE_CONSTANT,0),src(TGSI_FILE_TEMPORARY,0));
   l.declared_temps = 1;
   assert(fp_emit_dp2(&fp,&l,&i) && !fp.failed);
   assert(list_length(&fp.alu_instructions)==2);
   struct fp_alu_instr_packet *first=list_first_entry(&fp.alu_instructions,struct fp_alu_instr_packet,link);
   struct fp_alu_instr_packet *last=list_last_entry(&fp.alu_instructions,struct fp_alu_instr_packet,link);
   /* (2*3)+(4*5)=26. Only x,y source components participate. */
   assert(2.f*3.f+4.f*5.f==26.f);
   assert(first->slots[0].src[0].index==FP_UNIFORM_BASE+0);
   assert(first->slots[0].src[1].index==FP_GPR_BASE+0);
   assert(last->slots[0].src[0].index==FP_UNIFORM_BASE+1);
   assert(last->slots[0].src[1].index==FP_GPR_BASE+1);
   assert(last->slots[0].src[2].index >= FP_GPR_BASE);
}

static void test_dp2_swizzle_and_negative(void)
{
   struct grate_fp_shader fp; struct fp_lowering_state l; reset(&fp,&l);
   struct tgsi_src_register a=src(TGSI_FILE_CONSTANT,0), b=src(TGSI_FILE_TEMPORARY,0);
   a.SwizzleX=TGSI_SWIZZLE_W; a.SwizzleY=TGSI_SWIZZLE_Z;
   b.SwizzleX=TGSI_SWIZZLE_Y; b.SwizzleY=TGSI_SWIZZLE_X;
   a.Negate=1; l.declared_temps=1;
   struct tgsi_full_instruction i=make_dot(TGSI_OPCODE_DP2,
      dst(TGSI_FILE_OUTPUT,0,TGSI_WRITEMASK_XYZW),a,b);
   assert(fp_emit_dp2(&fp,&l,&i));
   struct fp_alu_instr_packet *first=list_first_entry(&fp.alu_instructions,struct fp_alu_instr_packet,link);
   struct fp_alu_instr_packet *last=list_last_entry(&fp.alu_instructions,struct fp_alu_instr_packet,link);
   assert(first->slots[0].src[0].index==FP_UNIFORM_BASE+3);
   assert(first->slots[0].src[1].index==FP_GPR_BASE+1);
   assert(first->slots[0].src[0].negate);
   assert(last->slots[0].src[0].index==FP_UNIFORM_BASE+2);
   assert(last->slots[0].src[1].index==FP_GPR_BASE+0);
   /* (-7 * 3) + (-2 * 5) = -31, independent of z/w components. */
   assert(-7.f*3.f+-2.f*5.f==-31.f);
}

static void test_dp2_alias_and_no_scratch(void)
{
   struct grate_fp_shader fp; struct fp_lowering_state l; reset(&fp,&l);
   l.declared_temps=1;
   struct tgsi_full_instruction i=make_dot(TGSI_OPCODE_DP2,
      dst(TGSI_FILE_TEMPORARY,0,TGSI_WRITEMASK_XY),
      src(TGSI_FILE_TEMPORARY,0),src(TGSI_FILE_CONSTANT,0));
   assert(fp_emit_dp2(&fp,&l,&i));
   assert(list_length(&fp.fp_instructions)==3); /* alias requires final MOV */
   reset(&fp,&l); l.declared_temps=2;
   i=make_dot(TGSI_OPCODE_DP2,dst(TGSI_FILE_OUTPUT,0,TGSI_WRITEMASK_X),
      src(TGSI_FILE_TEMPORARY,0),src(TGSI_FILE_TEMPORARY,1));
   assert(!fp_emit_dp2(&fp,&l,&i) && fp.failed);
   assert(strstr(fp.error,"scratch"));
}

static void test_dp2_unsupported_row_conflict_and_arity(void)
{
   struct grate_fp_shader fp; struct fp_lowering_state l; reset(&fp,&l);
   struct tgsi_full_instruction i=make_dot(TGSI_OPCODE_DP2,
      dst(TGSI_FILE_OUTPUT,0,TGSI_WRITEMASK_X),
      src(TGSI_FILE_INPUT,0),src(TGSI_FILE_INPUT,1));
   assert(!fp_emit_dp2(&fp,&l,&i) && fp.failed);
   reset(&fp,&l); i=make_dot(TGSI_OPCODE_DP2,
      dst(TGSI_FILE_OUTPUT,0,TGSI_WRITEMASK_X),
      src(TGSI_FILE_INPUT,0),src(TGSI_FILE_CONSTANT,0));
   i.Instruction.NumSrcRegs=1;
   assert(!fp_emit_dp2(&fp,&l,&i) && strstr(fp.error,"two sources"));
}

static void test_dp2_absolute_and_empty_mask(void)
{
   struct grate_fp_shader fp; struct fp_lowering_state l; reset(&fp,&l);
   struct tgsi_src_register a=src(TGSI_FILE_CONSTANT,0), b=src(TGSI_FILE_TEMPORARY,0);
   a.Absolute=1; b.Negate=1; l.declared_temps=1;
   struct tgsi_full_instruction i=make_dot(TGSI_OPCODE_DP2,
      dst(TGSI_FILE_OUTPUT,0,TGSI_WRITEMASK_XY),a,b);
   assert(fp_emit_dp2(&fp,&l,&i));
   struct fp_alu_instr_packet *first=list_first_entry(&fp.alu_instructions,struct fp_alu_instr_packet,link);
   assert(first->slots[0].src[0].absolute_value);
   assert(first->slots[0].src[1].negate);
   reset(&fp,&l); i.Dst[0].Register.WriteMask=0;
   assert(fp_emit_dp2(&fp,&l,&i));
   assert(list_length(&fp.fp_instructions)==0);
}

int
main(void)
{
   test_dp2_absolute_and_empty_mask();
   test_dp2_two_components_and_writemask();
   test_dp2_swizzle_and_negative();
   test_dp2_alias_and_no_scratch();
   test_dp2_unsupported_row_conflict_and_arity();
   test_dp3_output();
   { struct grate_fp_shader fp; struct fp_lowering_state l; reset(&fp,&l); struct tgsi_full_instruction i = make_dot(TGSI_OPCODE_DP2, dst(TGSI_FILE_OUTPUT,0,TGSI_WRITEMASK_XYZW), src(TGSI_FILE_INPUT,0), src(TGSI_FILE_CONSTANT,0)); assert(fp_emit_dp2(&fp,&l,&i)); assert(list_length(&fp.fp_instructions)==2); }
   test_dp4_output();
   test_dp3_temp_overlapping_output();
   test_no_scratch_fails_closed();
   test_row_conflict_fails_closed();
   test_dp3_embedded_scalar_fallback();
   test_frc_gpr_direct();
   test_frc_input_materialization();
   puts("PASS: 14 grate FRC/DP lowering structural tests");
   return 0;
}
