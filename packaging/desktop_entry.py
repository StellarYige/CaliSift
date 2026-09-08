import sys

if sys.argv[1:] == ["--self-check"]:
    from xingcheng.installation_check import run
    raise SystemExit(run())
else:
    from xingcheng.desktop import launch
    raise SystemExit(launch())
