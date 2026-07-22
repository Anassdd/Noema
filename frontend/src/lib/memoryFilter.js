// Cheap, client-side gate in front of the LLM memory judge. It answers a loose
// question: "could this user message plausibly state a durable fact?" When it
// says no, we skip the judge call entirely (saving a model round-trip). It's
// intentionally permissive — the LLM judge is the real filter; this only weeds
// out the obvious non-personal turns (plain questions, task requests, etc).

const SIGNALS = [
  // First-person self-description
  /\bi'?m\b/,
  /\bi am\b/,
  /\bi'?ve\b/,
  // Identity / naming
  /\bmy name is\b/,
  /\bcall me\b/,
  // First-person stable verbs (preferences, situation, habits)
  /\bi (prefer|like|love|enjoy|hate|dislike|want|need|use|work|live|study|speak|own|have|drive|play)\b/,
  // "my <attribute>" disclosures
  /\bmy (name|favou?rite|job|role|title|team|manager|company|goal|budget|email|phone|number|birthday|address|pronouns?)\b/,
  // Explicit memory intent
  /\bremember\b/,
  /\bfrom now on\b/,
  /\bplease (note|remember|keep in mind)\b/,
  // Corrections / retractions (drive update + delete operations)
  /\bactually\b/,
  /\bnot anymore\b/,
  /\bno longer\b/,
  /\bthat'?s (wrong|not right|outdated)\b/,
  /\bforget (that|what i said)\b/,
  /\bi (moved|changed|switched|stopped|started)\b/,
  // Asserted opinions (routed to the belief notes, not the fact list)
  /\bi (think|believe|disagree|agree|doubt)\b/,
  /\bin my (opinion|view|experience)\b/,
  /\bmy (view|take|opinion) (is|on)\b/,
  // ---- French (the company speaks it — parity with every group above) ----
  /\bje suis\b/,
  /\bj'ai\b/,
  /\bje m'appelle\b/,
  /\bappelle[jz]?-moi\b/,
  /\bje (prefere|préfère|aime|adore|deteste|déteste|veux|travaille|habite|vis|etudie|étudie|parle|utilise|possede|possède|joue|conduis)\b/,
  /\bm(on|a) (nom|prenom|prénom|poste|role|rôle|titre|equipe|équipe|manager|societe|société|entreprise|objectif|budget|email|telephone|téléphone|anniversaire|adresse|preference|préférence)\b/,
  /\b(retiens|souviens-toi|note bien|garde en tete|garde en tête)\b/,
  /\b(a|à) partir de maintenant\b/,
  /\bdesormais\b/,
  /\bdésormais\b/,
  // Corrections françaises
  /\ben fait\b/,
  /\bplus maintenant\b/,
  /\bce n'est plus\b/,
  /\bc'est (faux|errone|erroné|depasse|dépassé)\b/,
  /\boublie (ca|ça|ce que j'ai dit)\b/,
  /\bj'ai (demenage|déménagé|change|changé|arrete|arrêté|commence|commencé)\b/,
  // Opinions françaises
  /\bje (pense|crois|trouve|estime|doute)\b/,
  /\b(a|à) mon avis\b/,
  /\bselon moi\b/,
  /\bd'apres moi\b/,
  /\bd'après moi\b/,
];

// French text arrives with typographic apostrophes (’) and, from fast typing,
// often without accents — normalize both so one signal list matches all spellings.
function normalize(text) {
  return text.toLowerCase().replace(/[’‘]/g, "'");
}

export function looksMemorable(text) {
  const t = normalize(text);
  return SIGNALS.some((re) => re.test(t));
}

// Second pass over the ASSISTANT's reply: catch facts the user stated tersely
// (e.g. "lebanon") that the user-message filter misses, by spotting when the
// bot acknowledges personal info back ("you're from…", "got it…").
const REPLY_SIGNALS = [
  /\byou'?re from\b/,
  /\byou are from\b/,
  /\byour name is\b/,
  /\byou'?re called\b/,
  /\bnice to meet you\b/,
  /\byou live in\b/,
  /\byou'?re based in\b/,
  /\byou work (at|as|in)\b/,
  /\byou study\b/,
  /\byou prefer\b/,
  /\byou'?re an? \b/, // "you're a developer", "you're an engineer"
  /\bgot it\b/,
  /\bnoted\b/,
  /\bi'?ll remember\b/,
  /\bgood to know\b/,
  // ---- French acknowledgements ----
  /\b(vous etes|vous êtes|tu es)\b/,
  /\b(vous habitez|tu habites)\b/,
  /\b(vous travaillez|tu travailles)\b/,
  /\b(vous preferez|vous préférez|tu preferes|tu préfères)\b/,
  /\b(vous vous appelez|tu t'appelles)\b/,
  /\benchante\b/,
  /\benchanté\b/,
  /\bc'est note\b/,
  /\bc'est noté\b/,
  /\bbien note\b/,
  /\bbien noté\b/,
  /\bje m'en souviendrai\b/,
  /\bje retiens\b/,
  /\bbon (a|à) savoir\b/,
];

export function replyLooksMemorable(answer) {
  const t = answer.toLowerCase().replace(/[’‘]/g, "'");
  return REPLY_SIGNALS.some((re) => re.test(t));
}

// Gate in front of archive recall: does the message ask about the user's own
// past or an earlier conversation? Only then is the history/journal archive
// searched and injected one-off (it costs zero context otherwise).
const PAST_SIGNALS = [
  /\bwhen (was|did|have) i\b/,
  /\b(was|did|have|had) i\b.*\b(ever|before|already|last)\b/,
  /\bhave i (ever )?been\b/,
  /\bwhat did (i|we)\b/,
  /\blast (time|week|month|year)\b/,
  /\bremember when\b/,
  /\b(we|you and i) (talked|spoke|discussed|worked on)\b/,
  /\b(earlier|previous|last) (chat|conversation|discussion|session)\b/,
  /\bwhat (were|was) (we|i) (doing|working on)\b/,
  // ---- French ----
  /\bquand (est-ce que )?j'(ai|etais|étais)\b/,
  /\b(ou|où) (etais-je|étais-je|j'etais|j'étais)\b/,
  /\best-ce que j'(ai|etais|étais)\b.*\b(deja|déjà|avant)\b/,
  /\bde quoi (on a|avons-nous|a-t-on) parl(e|é)\b/,
  /\bla derni(ere|ère) fois\b/,
  /\b(conversation|discussion) pr(ecedente|écédente)\b/,
  /\bsouviens-toi quand\b/,
];

export function looksPastReferential(text) {
  const t = normalize(text);
  return PAST_SIGNALS.some((re) => re.test(t));
}
