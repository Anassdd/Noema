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
];

export function looksMemorable(text) {
  const t = text.toLowerCase();
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
];

export function replyLooksMemorable(answer) {
  const t = answer.toLowerCase();
  return REPLY_SIGNALS.some((re) => re.test(t));
}
