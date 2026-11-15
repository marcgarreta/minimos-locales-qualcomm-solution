"""Enable llamafile's tiled Q8_0/Q4_0 GEMM (tinyBLAS_Q0_ARM) on ARMv8.0 cores without dotprod (Cortex-A53).

Upstream only builds it with __ARM_FEATURE_DOTPROD, so on the A53 every prompt matmul falls back to the
untiled vec_dot loop. Here the 32-wide block dot product is emulated with SMULL/SMLAL + SADALP, and the
A and B blocks of a tile are loaded once per k step (register reuse matters on an in-order core).
"""
import re, sys

path = sys.argv[1]
s = open(path).read()

old_guard = "#if defined(__ARM_FEATURE_DOTPROD)\ntemplate <typename TA>\nclass tinyBLAS_Q0_ARM {"
assert old_guard in s, "class guard not found"
s = s.replace(old_guard, "#if defined(__ARM_NEON)\ntemplate <typename TA>\nclass tinyBLAS_Q0_ARM {")
s = s.replace("#endif // __ARM_FEATURE_DOTPROD", "#endif // __ARM_NEON (tinyBLAS_Q0_ARM)")

# dispatch: both the Q8_0 and the Q4_0 cases
n = s.count("#elif defined(__ARM_FEATURE_DOTPROD)\n        tinyBLAS_Q0_ARM<")
assert n == 2, n
s = s.replace("#elif defined(__ARM_FEATURE_DOTPROD)\n        tinyBLAS_Q0_ARM<", "#elif defined(__ARM_NEON)\n        tinyBLAS_Q0_ARM<")

# new inner kernel
start = s.index("    template <int RM, int RN>\n    NOINLINE void gemm(int64_t m0, int64_t m, int64_t n0, int64_t n) {",
                s.index("class tinyBLAS_Q0_ARM {"))
end = s.index("    inline int8x16_t load_lo(const block_q8_0 *b) {", start)
kernel = r'''    template <int RM, int RN>
    NOINLINE void gemm(int64_t m0, int64_t m, int64_t n0, int64_t n) {
        int64_t ytiles = (m - m0) / RM;
        int64_t xtiles = (n - n0) / RN;
        int64_t tiles = xtiles * ytiles;
        int64_t duty = (tiles + nth - 1) / nth;
        int64_t start = duty * ith;
        int64_t end = start + duty;
        if (end > tiles)
            end = tiles;
        for (int64_t job = start; job < end; ++job) {
            int64_t ii = m0 + job / xtiles * RM;
            int64_t jj = n0 + job % xtiles * RN;
            float32x4_t Cv[RN][RM] = {};
            for (int64_t l = 0; l < k; ++l) {
                int8x16_t alo[RM], ahi[RM], blo[RN], bhi[RN];
                float da[RM], db[RN];
                for (int64_t i = 0; i < RM; ++i) {
                    const TA *a = A + lda * (ii + i) + l;
                    alo[i] = load_lo(a); ahi[i] = load_hi(a); da[i] = unhalf(a->d);
                }
                for (int64_t j = 0; j < RN; ++j) {
                    const block_q8_0 *b = B + ldb * (jj + j) + l;
                    blo[j] = load_lo(b); bhi[j] = load_hi(b); db[j] = unhalf(b->d);
                }
                for (int64_t j = 0; j < RN; ++j)
                    for (int64_t i = 0; i < RM; ++i)
                        Cv[j][i] = vmlaq_n_f32(Cv[j][i], vcvtq_f32_s32(dot32(alo[i], ahi[i], blo[j], bhi[j])),
                                               da[i] * db[j]);
            }
            for (int64_t j = 0; j < RN; ++j)
                for (int64_t i = 0; i < RM; ++i)
                    C[ldc * (jj + j) + (ii + i)] = hsum(Cv[j][i]);
        }
    }

#if defined(__ARM_FEATURE_DOTPROD)
    static inline int32x4_t dot32(int8x16_t alo, int8x16_t ahi, int8x16_t blo, int8x16_t bhi) {
        return vdotq_s32(vdotq_s32(vdupq_n_s32(0), alo, blo), ahi, bhi);
    }
#else
    // 32 int8 products summed into 4 int32 lanes (lane order differs from SDOT; only the total is used).
    // q4_0 weights are in [-8, 7]: four products per int16 lane cannot overflow (4*8*127 < 32767).
    // q8_0 values are in [-127, 127]: two products per int16 lane at most (2*127*127 < 32767).
    static inline int32x4_t dot32(int8x16_t alo, int8x16_t ahi, int8x16_t blo, int8x16_t bhi) {
        if constexpr (std::is_same<TA, block_q4_0>::value) {
            int16x8_t p = vmull_s8(vget_low_s8(alo), vget_low_s8(blo));
            p = vmlal_s8(p, vget_high_s8(alo), vget_high_s8(blo));
            p = vmlal_s8(p, vget_low_s8(ahi), vget_low_s8(bhi));
            p = vmlal_s8(p, vget_high_s8(ahi), vget_high_s8(bhi));
            return vpaddlq_s16(p);
        } else {
            int16x8_t p0 = vmull_s8(vget_low_s8(alo), vget_low_s8(blo));
            p0 = vmlal_s8(p0, vget_high_s8(alo), vget_high_s8(blo));
            int16x8_t p1 = vmull_s8(vget_low_s8(ahi), vget_low_s8(bhi));
            p1 = vmlal_s8(p1, vget_high_s8(ahi), vget_high_s8(bhi));
            return vpadalq_s16(vpaddlq_s16(p0), p1);
        }
    }
#endif

'''
s = s[:start] + kernel + s[end:]
if "#include <type_traits>" not in s:
    s = "#include <type_traits>\n" + s
open(path, "w").write(s)
print("patched", path)
