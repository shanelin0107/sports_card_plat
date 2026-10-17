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
  'lazer', 'laser', 'sparkle', 'glitter', 'pulsar', 'nebula', 'tiger', 'zebra', 'fluorescent', 'galactic', 'kaleidoscope',
  'atomic', 'lava', 'speckle', 'raywave', 'geometric', 'checkerboard', 'aqua', 'yellow', 'peacock', 'stars', 'logo',
];

// Team nicknames show up in almost every listing title; they are never part of the player's name.
const TEAMS = new Set(
  (
    // NFL
    'cardinals falcons ravens bills panthers bears bengals browns cowboys broncos lions packers texans colts jaguars chiefs ' +
    'raiders chargers rams dolphins vikings patriots saints giants jets eagles steelers 49ers niners seahawks buccaneers bucs titans commanders ' +
    // NBA
    'hawks celtics nets hornets bulls cavaliers cavs mavericks mavs nuggets pistons warriors rockets pacers clippers lakers grizzlies heat ' +
    'bucks timberwolves wolves pelicans knicks thunder magic 76ers sixers suns blazers trail kings spurs raptors jazz wizards ' +
    // MLB
    'diamondbacks dbacks braves orioles sox cubs reds guardians rockies tigers astros royals angels dodgers marlins brewers twins mets yankees ' +
    'athletics phillies pirates padres mariners rays rangers jays nationals ' +
    // NHL
    'ducks coyotes bruins sabres flames hurricanes blackhawks avalanche blue jackets stars wings oilers ' +
    'predators devils islanders senators flyers penguins sharks kraken blues lightning leafs canucks knights capitals jets ' +
    // F1
    'ferrari mercedes mclaren williams alpine haas sauber aston martin bull racing bulls'
  ).split(' '),
);
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
  // "F1" / "Formula 1" / "Formula One" names the sport and belongs to the set ("Topps Chrome F1"),
  // never to the player or the card number.
  const f1 = q.match(/\b(f1|formula\s*(?:1|one))\b/i);
  if (f1) {
    g.sport = 'F1';
    q = q.replace(f1[0], ' ');
  }

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
  if (f1) g.set_name = g.set_name ? `${g.set_name} F1` : 'F1';
  for (const b of BRANDS) {
    if (new RegExp(`\\b${b}\\b`, 'i').test(q)) {
      g.brand = g.brand ?? title(b);
      q = q.replace(new RegExp(`\\b${b}\\b`, 'i'), ' ');
    }
  }

  // Team names that contain a colour would otherwise read as a parallel ("Red Bull" -> "Red").
  q = q.replace(/\b(oracle red bull racing|red bull racing|red bull|red sox|white sox|blue jays|red wings|blue jackets|golden state|golden knights|aston martin|racing bulls|trail blazers)\b/gi, ' ');
  const words = q.split(/\s+/).filter(Boolean);
  const parallel = words.filter((w) => PARALLEL_WORDS.includes(w.toLowerCase()));
  // A leftover "Prizm"/"Refractor" after the set was found names the parallel ("Lazer Prizm", "Gold Refractor").
  const tail = parallel.length ? words.find((w) => /^(prizm|prizms)$/i.test(w)) : undefined;
  if (parallel.length) g.parallel = title([...parallel, ...(tail ? [tail] : [])].join(' ').toLowerCase());
  const player = words.filter(
    (w) =>
      !PARALLEL_WORDS.includes(w.toLowerCase()) &&
      !NOISE.has(w.toLowerCase()) &&
      !TEAMS.has(w.toLowerCase()) &&
      !/^(prizm|prizms|refractor|chrome|parallel|insert|ssp|sp|numbered|card|cards|nfl|nba|mlb|nhl|f1)$/i.test(w) &&
      !/\d/.test(w) &&
      !/^[^a-z]+$/i.test(w),
  );
  if (player.length) g.player = title(player.join(' ').toLowerCase());
  return g;
}
