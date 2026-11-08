#!/usr/bin/env bash
set -euo pipefail
ABLATION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ABLATION_DEPS="$ABLATION_ROOT/06_reports/latex_dependencies"
ABLATION_TREE="$ABLATION_DEPS/verified_texmf/usr/share/texlive/texmf-dist"
export TEXINPUTS="$ABLATION_DEPS/ctan//:$ABLATION_TREE/tex//:"
export TFMFONTS="$ABLATION_TREE/fonts/tfm//:"
export VFFONTS="$ABLATION_TREE/fonts/vf//:"
export T1FONTS="$ABLATION_TREE/fonts/type1//:"
export ENCFONTS="$ABLATION_TREE/fonts/enc//:"
cd "$ABLATION_ROOT/.."
ABLATION_BUILD="$ABLATION_ROOT/06_reports/paper_build"
mkdir -p "$ABLATION_BUILD"
for ABLATION_PASS in 1 2 3; do
  taskset -c 1 pdflatex -interaction=nonstopmode -halt-on-error \
    -jobname=SecPaper_Yaqi-2-Hybrid-Ablation -output-directory="$ABLATION_BUILD" \
    IEEE-conference-template-062824.tex > "$ABLATION_BUILD/compile_pass${ABLATION_PASS}.txt" 2>&1
done
printf '%s\n' "$ABLATION_BUILD/SecPaper_Yaqi-2-Hybrid-Ablation.pdf"
