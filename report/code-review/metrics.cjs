const ts = require(process.argv[2]);
const fs = require('fs'), path = require('path');
const dir = process.argv[3];
const files = fs.readdirSync(dir).filter(f => f.endsWith('.ts'));
const fns = []; let maxNest = {d:0}; let code=0, comment=0, magic=0, big=[];
for (const f of files) {
  const txt = fs.readFileSync(path.join(dir,f),'utf8');
  const lines = txt.split('\n'); if (lines.length>500) big.push(f+':'+lines.length);
  for (const l of lines){const t=l.trim(); if(!t) continue; if(t.startsWith('//')||t.startsWith('*')||t.startsWith('/*')) comment++; else code++;}
  const sf = ts.createSourceFile(f, txt, ts.ScriptTarget.Latest, true);
  const isFn = n => ts.isFunctionDeclaration(n)||ts.isMethodDeclaration(n)||ts.isArrowFunction(n)||ts.isFunctionExpression(n)||ts.isConstructorDeclaration(n)||ts.isGetAccessor(n);
  const isBlockNest = n => ts.isIfStatement(n)||ts.isForStatement(n)||ts.isForOfStatement(n)||ts.isForInStatement(n)||ts.isWhileStatement(n)||ts.isDoStatement(n)||ts.isSwitchStatement(n)||ts.isTryStatement(n);
  function cc(n){ let c=1; (function w(x){ if(x!==n && isFn(x)) return; if(ts.isIfStatement(x)||ts.isForStatement(x)||ts.isForOfStatement(x)||ts.isForInStatement(x)||ts.isWhileStatement(x)||ts.isDoStatement(x)||ts.isCaseClause(x)||ts.isConditionalExpression(x)||ts.isCatchClause(x)) c++; if(ts.isBinaryExpression(x)&&[ts.SyntaxKind.AmpersandAmpersandToken,ts.SyntaxKind.BarBarToken,ts.SyntaxKind.QuestionQuestionToken].includes(x.operatorToken.kind)) c++; ts.forEachChild(x,w);})(n); return c; }
  function walk(n, depth){
    if (isFn(n)) { const s=sf.getLineAndCharacterOfPosition(n.getStart()).line, e=sf.getLineAndCharacterOfPosition(n.end).line; let name=(n.name&&n.name.getText&&n.name.getText())||(ts.isVariableDeclaration(n.parent)?n.parent.name.getText():'<anon>'); if(e-s+1>=3||!ts.isArrowFunction(n)) fns.push({f,name,len:e-s+1,cc:cc(n),line:s+1}); depth=0; }
    if (isBlockNest(n)) { depth++; if(depth>maxNest.d) maxNest={d:depth,at:f+':'+(sf.getLineAndCharacterOfPosition(n.getStart()).line+1)}; }
    if (ts.isNumericLiteral(n)) { const v=Number(n.text); const p=n.parent; const inConst = ts.isVariableDeclaration(p)&&p.parent.flags&ts.NodeFlags.Const && ts.isSourceFile(p.parent.parent.parent); if(![0,1,2,-1,100].includes(v) && !inConst && !ts.isPropertyAssignment(p) && !ts.isArrayLiteralExpression(p) && !(ts.isPrefixUnaryExpression(p)&&ts.isArrayLiteralExpression(p.parent))) magic++; }
    ts.forEachChild(n, c=>walk(c,depth));
  }
  walk(sf,0);
}
const lens=fns.map(x=>x.len).sort((a,b)=>a-b); const q=p=>lens[Math.min(lens.length-1,Math.floor(p*lens.length))];
const top=[...fns].sort((a,b)=>b.len-a.len).slice(0,5);
console.log(JSON.stringify({nFns:fns.length, median:q(0.5), p90:q(0.9), max:lens[lens.length-1], over50:lens.filter(l=>l>50).length, big, maxNest, commentRatio:(comment/(code+comment)).toFixed(2), magicPer1k:(magic/code*1000).toFixed(1), top:top.map(t=>`${t.f}:${t.line} ${t.name} len=${t.len} cc=${t.cc}`)},null,1));
