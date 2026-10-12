// Best-effort parse of a collector's search ("2024-25 prizm black Damian Lillard #12 RC")
// into new-card form defaults. Everything stays editable; this only saves typing.

export type CardGuess = {
  print_run?: string;
  year?: string;
  brand?: string;
  set_name?: string;
  player?: string;
  card_number?: string;
  parallel?: string;
  sport?: string;
  rookie?: boolean;
};

const SETS: [string, string, string][] = [
  // [phrase, brand, set]
  ['national treasures', 'Panini', 'National Treasures'],
  ['prizm black', 'Panini', 'Prizm Black'],
  ['prizm deca', 'Panini', 'Prizm Deca'],
  ['prizm monopoly', 'Panini', 'Prizm Monopoly'],
  ['prizm draft picks', 'Panini', 'Prizm Draft Picks'],
  ['select black', 'Panini', 'Select Black'],
  ['topps chrome black', 'Topps', 'Chrome Black'],
  ['donruss optic', 'Panini', 'Donruss Optic'],
  ['stadium club', 'Topps', 'Stadium Club'],
  ['bowman chrome', 'Bowman', 'Bowman Chrome'],
  ['topps chrome', 'Topps', 'Chrome'],
  ['prizm', 'Panini', 'Prizm'],
  ['select', 'Panini', 'Select'],
  ['optic', 'Panini', 'Donruss Optic'],
  ['mosaic', 'Panini', 'Mosaic'],
  ['donruss', 'Panini', 'Donruss'],
  ['hoops', 'Panini', 'NBA Hoops'],
  ['contenders', 'Panini', 'Contenders'],
  ['flawless', 'Panini', 'Flawless'],
  ['immaculate', 'Panini', 'Immaculate'],
  ['chrome', 'Topps', 'Chrome'],
  ['heritage', 'Topps', 'Heritage'],
  ['finest', 'Topps', 'Finest'],
  ['update', 'Topps', 'Update'],
  ['bowman', 'Bowman', 'Bowman'],
  ['upper deck', 'Upper Deck', 'Upper Deck'],
  ['young guns', 'Upper Deck', 'Young Guns'],
];
const BRANDS = ['panini', 'topps', 'bowman', 'upper deck', 'leaf', 'fleer'];
const PARALLEL_WORDS = [
  'silver', 'black', 'gold', 'red', 'blue', 'green', 'orange', 'purple', 'pink', 'white', 'bronze', 'teal',
  'holo', 'refractor', 'mojo', 'wave', 'shimmer', 'disco', 'hyper', 'scope', 'camo', 'cracked', 'ice',
  'tie-dye', 'neon', 'snakeskin', 'velocity', 'fast', 'break', 'choice', 'mojo', 'xfractor', 'sapphire',
];
const NOISE = new Set(['rc', 'rookie', 'psa', 'bgs', 'sgc', 'cgc', 'auto', 'autograph', 'card', 'base', 'raw', 'gem', 'mint', 'mt']);

const title = (s: string) => s.replace(/\b[a-z]/g, (c) => c.toUpperCase());

export function guessCard(query: string): CardGuess {
  let q = ` ${query.trim()} `;
  const g: CardGuess = {};

  const season = q.match(/\b((?:19|20)\d{2})\s*[-/]\s*\d{2,4}\b/);
  const year = season ?? q.match(/\b((?:19|20)\d{2})\b/);
  if (year) {
    g.year = year[1];
    q = q.replace(year[0], ' ');
  }
  if (season) g.sport = 'Basketball'; // "2024-25" style seasons are NBA/NHL; editable

  // Serial numbering ("/60", "12/60", "#/60") is a print run, not part of the name or card number.
  const serial = q.match(/(?:#?\s*\d{0,4})\s*\/\s*(\d{1,4})\b/);
  if (serial) {
    g.print_run = serial[1];
    q = q.replace(serial[0], ' ');
  }

  const num = q.match(/#\s*([A-Za-z0-9-]+)/);
  if (num) {
    g.card_number = num[1];
    q = q.replace(num[0], ' ');
  } else {
    // Insert / auto codes without "#": "DS-LIN", "RA-JL", "BCP-50"
    const code = q.match(/\b([A-Z]{1,5}-[A-Z0-9]{1,6})\b/);
    if (code) {
      g.card_number = code[1];
      q = q.replace(code[0], ' ');
    }
  }
  q = q.replace(/\b(psa|bgs|sgc|cgc)\s*\d+(\.5)?\b/gi, ' ');
  if (/\b(rc|rookie)\b/i.test(q)) g.rookie = true;

  const lower = q.toLowerCase();
  const set = SETS.find(([phrase]) => new RegExp(`\\b${phrase}\\b`).test(lower));
  if (set) {
    g.brand = set[1];
    g.set_name = set[2];
    q = q.replace(new RegExp(`\\b${set[0]}\\b`, 'i'), ' ');
  }
  for (const b of BRANDS) {
    if (new RegExp(`\\b${b}\\b`, 'i').test(q)) {
      g.brand = g.brand ?? title(b);
      q = q.replace(new RegExp(`\\b${b}\\b`, 'i'), ' ');
    }
  }

  const words = q.split(/\s+/).filter(Boolean);
  const parallel = words.filter((w) => PARALLEL_WORDS.includes(w.toLowerCase()));
  if (parallel.length) g.parallel = title(parallel.join(' ').toLowerCase());
  const player = words.filter(
    (w) => !PARALLEL_WORDS.includes(w.toLowerCase()) && !NOISE.has(w.toLowerCase()) && !/\d/.test(w) && !/^[^a-z]+$/i.test(w),
  );
  if (player.length) g.player = title(player.join(' ').toLowerCase());
  return g;
}
