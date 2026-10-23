import pathlib
import shutil
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
build = root / 'axiom_selection/build'
objects = 'index_lits forward_subsume demodulate pred_elim unfold semantics white_black actions search utilities provers foffer'.split()

def main():
    build.mkdir(exist_ok = True)
    subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', str(root / 'axiom_selection/native_search.c'), '-o', str(build / 'native-search')], check = True)
    shutil.copyfile(build / 'native-search', build / 'native-search-control')
    (build / 'native-search-control').chmod(0o755)
    subprocess.run(['make', '-C', str(root / 'ladr'), '-j8', 'lib'], check = True)
    subprocess.run(['make', '-C', str(root / 'provers.src'), '-j8', 'prover9'], check = True)
    for source, name in [('provers.src/giv_select.c', 'giv_select'), ('axiom_selection/selection.c', 'selection')]:
        subprocess.run(['gcc', '-O', '-Wall', '-DPROVER9_TOROK', '-c', str(root / source), '-o', str(build / f'{name}.o')], check = True)

    inputs = [root / 'provers.src' / f'{name}.o' for name in ['prover9'] + objects]
    inputs += [build / 'giv_select.o', build / 'selection.o', root / 'ladr/libladr.a']
    subprocess.run(['gcc', '-o', str(build / 'prover9-torok'), *map(str, inputs), '-lm'], check = True)
    shutil.copyfile(build / 'prover9-torok', build / 'prover9-soft')
    (build / 'prover9-soft').chmod(0o755)

if __name__ == '__main__':
    main()
