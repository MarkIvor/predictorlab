from pathlib import Path

p = Path("frontend/src/pages/model/ApiTab.tsx")
s = p.read_text(encoding="utf-8")
s = s.replace("import { fmtShort } from '../../design/components'\n", "")
s = s.replace(
    "import { Globe, Key, Upload, Copy, Check, ExternalLink, Lock, Link2, FileSpreadsheet, Zap } from 'lucide-react'",
    "import { Globe, Key, Upload, Copy, Check, ExternalLink, Lock, Link2, FileSpreadsheet, Zap, TrendingUp, Brain, ShieldCheck } from 'lucide-react'",
)
p.write_text(s, encoding="utf-8")

p = Path("frontend/src/pages/model/Overview.tsx")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "import { AccentTile, BarChart, StatTile, fmtShort } from '../../design/components'",
    "import { AccentTile, BarChart, fmtShort } from '../../design/components'",
)
p.write_text(s, encoding="utf-8")

p = Path("frontend/src/pages/PublicPage.tsx")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "import { Globe, Lock, Loader2, TrendingUp, ShieldCheck, Zap } from 'lucide-react'",
    "import { Lock, Loader2, TrendingUp, ShieldCheck, Zap } from 'lucide-react'",
)
p.write_text(s, encoding="utf-8")

print("fixed")
