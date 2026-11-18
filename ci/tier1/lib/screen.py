# usage: screen.py FILE...  Exit 1 if any file matches a sensitive-content pattern.
# Prints only "<file>: <pattern name>" for matches, never the matching content.
import os, re, sys
PATTERNS = {
    "github-token": r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
    "aws-access-key": r"AKIA[0-9A-Z]{16}",
    "private-key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "auth-header": r"(?i)authorization:\s*(bearer|basic|token)\s+\S",
    "credential-assignment": r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?tokens?)\s*[=:]\s*\S{6,}",
    "actions-runtime-token": r"ACTIONS_(RUNTIME|ID_TOKEN_REQUEST)_(TOKEN|URL)",
    "url-with-credentials": r"https?://[^/\s:@]+:[^/\s@]+@",
    "email-address": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.(com|org|net|edu|gov|io|de|it|uk|eu|fr|nl|ch|at|se|fi|dk|no|es|pl|cz|hu|cn|jp|kr|in|us|ca|au|info)\b",
    "private-path": r"(?<![\w/.-])(/root/|/Users/|/var/root/|/home/(?!runner/))",
}
bad = 0
for f in sys.argv[1:]:
    try:
        text = open(f, encoding="utf-8", errors="strict").read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"{os.path.basename(f)}: unreadable-or-not-utf8"); bad = 1; continue
    for name, rx in PATTERNS.items():
        if re.search(rx, text):
            print(f"{os.path.basename(f)}: {name}"); bad = 1
sys.exit(bad)
