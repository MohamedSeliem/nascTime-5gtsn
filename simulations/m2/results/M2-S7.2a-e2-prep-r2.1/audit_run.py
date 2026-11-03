"""file-open audit: runs a checker's main() in-process and logs every file opened for reading (path, mode)"""
import sys, os, runpy
log = open(sys.argv[1], "w")
seen = set()
def hook(ev, args):
    if ev == "open":
        p, mode = args[0], args[1]
        if isinstance(p, (str, bytes)) and (mode is None or "r" in str(mode)):
            p = os.path.realpath(p if isinstance(p, str) else p.decode())
            if p not in seen:
                seen.add(p); log.write(p + "\n"); log.flush()
sys.addaudithook(hook)
script = sys.argv[2]
sys.argv = [script] + sys.argv[3:]
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(script))))
runpy.run_path(script, run_name="__main__")
