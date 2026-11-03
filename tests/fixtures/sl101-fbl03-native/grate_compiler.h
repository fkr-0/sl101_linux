#ifndef GRATE_COMPILER_H
#define GRATE_COMPILER_H

#include "util/list.h"

#include <stdbool.h>
#include <stdint.h>

#define GRATE_COMPILE_ERROR_LEN 192

struct tgsi_parse_context;

struct grate_vp_shader {
   struct list_head instructions;
   uint16_t output_mask;
   unsigned num_immediates;
   uint32_t immediates[256][4];
   bool failed;
   char error[GRATE_COMPILE_ERROR_LEN];
};

struct grate_fp_info {
   struct {
      uint32_t src;
      uint32_t dst;
   } inputs[16];
   int num_inputs;
   int color_input;
   int max_tram_row;
   unsigned pseq_to_dw_exec_nb;
};

struct grate_fp_shader {
   struct list_head fp_instructions;
   struct list_head alu_instructions;
   struct list_head mfu_instructions;
   struct grate_fp_info info;
   unsigned num_immediates;
   float immediates[256][4];
   bool failed;
   char error[GRATE_COMPILE_ERROR_LEN];
};

void
grate_tgsi_to_vp(struct grate_vp_shader *vp, struct tgsi_parse_context *tgsi);

void
grate_tgsi_to_fp(struct grate_fp_shader *fp, struct tgsi_parse_context *tgsi);

bool
grate_fp_enable_premultiplied_src_over(struct grate_fp_shader *fp);

#endif
