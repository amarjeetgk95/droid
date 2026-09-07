import re
from pathlib import Path

p = Path('docs/OPTIONS_INTELLIGENCE_ROBUSTNESS_REVIEW.md')
text = p.read_text(encoding='utf-8')

for idx, ln in enumerate(text.splitlines()):
    if 'erved' in ln or ',,' in ln or 'is Falseand' in ln or 'validis False' in ln:
        print('GOT:', idx + 1, repr(ln))

text = re.sub(r'band\s+erved\s+0\.5%', 'band ~0.5%', text)
text = re.sub(r'solve_iv\(17746\.23,{1,}?\s*24000,{1,}?\s*0\.02,{1,}?\s*"CE"\)is None',
              'solve_iv(17746.23, 24900, 24000, 0.02, "CE") is None', text)
text = re.sub(r'res\.is_viableis Falseand res\.non_viability_reasons',
              'res.is_viable is False and res.non_viability_reasons', text)
text = re.sub(r'ctx\.market_data_validis False', 'ctx.market_data_valid is False', text)

p.write_text(text, encoding='utf-8')
check = p.read_text(encoding='utf-8')
print('REMAIN:', check.count('erved'), 'erved |', check.count(',,'), 'dcomma |',
      check.count('is Falseand'), 'glued')