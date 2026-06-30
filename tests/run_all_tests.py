import traceback
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))

def load_mod(name: str):
    path = ROOT / f"{name}.py"
    return SourceFileLoader(name, str(path)).load_module()

test_adapters = load_mod("test_adapters")
test_ontology = load_mod("test_ontology")
test_semantic = load_mod("test_semantic")
test_transformation = load_mod("test_transformation")
test_projection = load_mod("test_projection")
test_validation = load_mod("test_validation")
test_cli = load_mod("test_cli")


def run_module_tests(mod):
    failures = 0
    for name in dir(mod):
        if name.startswith("test_"):
            fn = getattr(mod, name)
            if callable(fn):
                try:
                    fn()
                    print(f"OK: {mod.__name__}.{name}")
                except Exception:
                    failures += 1
                    print(f"FAIL: {mod.__name__}.{name}")
                    traceback.print_exc()
    return failures


def main():
    total_fail = 0
    total_fail += run_module_tests(test_adapters)
    total_fail += run_module_tests(test_ontology)
    total_fail += run_module_tests(test_semantic)
    total_fail += run_module_tests(test_transformation)
    total_fail += run_module_tests(test_projection)
    total_fail += run_module_tests(test_validation)
    total_fail += run_module_tests(test_cli)
    if total_fail:
        print(f"Tests failed: {total_fail}")
        sys.exit(1)
    print("All tests passed")


if __name__ == "__main__":
    main()
