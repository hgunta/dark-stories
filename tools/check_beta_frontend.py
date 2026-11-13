"""Verify beta HTML structure and inline JavaScript syntax with Node."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile

class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack=[]
        self.ids={}
        self.inline=[]
        self.in_script=False
        self.script=[]
        self.feedback_parent=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in {"script","style","link","img","input","meta","br","hr","path","rect","circle","line","polyline","polygon","ellipse","stop","use"}:
            if tag=="script" and not a.get("src"):self.in_script=True;self.script=[]
        else:self.stack.append(tag)
        if "id" in a:
            self.ids[a["id"]]=self.ids.get(a["id"],0)+1
            if a["id"]=="feedback-panel":
                self.feedback_parent=self.stack[-2:] if len(self.stack)>1 else self.stack[:]
        if a.get("id")=="playtest-opt-in" and "checked" in a:
            raise AssertionError("Consent checkbox must never be prechecked")
    def handle_endtag(self,tag):
        if tag=="script" and self.in_script:
            self.in_script=False
            self.inline.append("".join(self.script))
        if self.stack and self.stack[-1]==tag:self.stack.pop()
    def handle_data(self,data):
        if self.in_script:self.script.append(data)

def main():
    page=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    parsed=Inspector();parsed.feed(page)
    assert parsed.ids.get("feedback-panel")==1,parsed.ids
    assert parsed.ids.get("playtest-opt-in")==1
    assert parsed.ids.get("feedback-parking")==1
    assert all(count==1 for count in parsed.ids.values()), "Duplicate HTML element IDs"
    assert parsed.inline,"No inline JavaScript to check"
    for script in parsed.inline:
        with tempfile.NamedTemporaryFile(mode="w",suffix=".js",encoding="utf-8") as f:
            f.write(script);f.flush()
            subprocess.run(["node","--check",f.name],check=True)
    print("PASS: beta HTML element IDs and inline JavaScript syntax")

if __name__=="__main__":main()
