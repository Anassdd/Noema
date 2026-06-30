"""Stopwords removed before building the co-occurrence network.

Multilingual on purpose — the corpus is largely French (a French company) with
English research papers mixed in, so both lists are merged. Kept deliberately
compact: function words and the most frequent fillers, not an exhaustive lexicon.
"""

from __future__ import annotations

_ENGLISH = """
a about above after again against all am an and any are aren't as at be because
been before being below between both but by can cannot could couldn't did didn't
do does doesn't doing don't down during each few for from further had hadn't has
hasn't have haven't having he her here hers herself him himself his how however i
if in into is isn't it its itself just let me more most my myself no nor not of off
on once only or other ought our ours ourselves out over own same shan't she should
shouldn't so some such than that the their theirs them themselves then there these
they this those through to too under until up very was wasn't we were weren't what
when where which while who whom why will with won't would wouldn't you your yours
yourself yourselves also may might must shall upon within without among across
toward towards able etc via per use used using one two three new like get got make
made many much well still even way thing things
"""

_FRENCH = """
au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais
me même mes moi mon ne nos notre nous on ou où par pas pour qu que qui sa se ses
son sur ta te tes toi ton tu un une vos votre vous c d j l à m n s t y été étée
étées étés étant suis es est sommes êtes sont serai seras sera serons serez seront
serais serait serions seriez seraient étais était étions étiez étaient fus fut
fûmes fûtes furent sois soit soyons soyez soient fusse fusses fût fussions fussiez
fussent ayant eu eue eues eus ai as avons avez ont aurai auras aura aurons aurez
auront aurais aurait aurions auriez auraient avais avait avions aviez avaient eut
eûmes eûtes eurent aie aies ait ayons ayez aient eusse eusses eût eussions eussiez
eussent ceci cela cet cette ici ils les leurs quel quels quelle quelles sans soi
plus très donc aussi alors comme entre tout tous toute toutes peut être cela ainsi
chaque dont selon afin lors deux trois fait faire dit cas
"""

STOPWORDS: frozenset[str] = frozenset(_ENGLISH.split()) | frozenset(_FRENCH.split())
