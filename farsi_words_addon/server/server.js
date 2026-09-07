const express = require("express");
const Database = require("better-sqlite3");
const path = require("path");
const fs = require("fs");
const { execFile } = require("child_process");

const DATA_DIR = "/data";
const AUDIO_DIR = path.join(DATA_DIR, "audio");
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(AUDIO_DIR)) fs.mkdirSync(AUDIO_DIR, { recursive: true });

const db = new Database(path.join(DATA_DIR, "words.db"));

db.exec(`
  CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    english TEXT NOT NULL,
    translit TEXT NOT NULL,
    farsi TEXT,
    has_audio INTEGER DEFAULT 0,
    added_by TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  )
`);

// Migrate older databases that predate the farsi/has_audio columns
const existingCols = db.prepare("PRAGMA table_info(words)").all().map((c) => c.name);
if (!existingCols.includes("farsi")) db.exec("ALTER TABLE words ADD COLUMN farsi TEXT");
if (!existingCols.includes("has_audio")) db.exec("ALTER TABLE words ADD COLUMN has_audio INTEGER DEFAULT 0");
if (!existingCols.includes("farsi_norm")) db.exec("ALTER TABLE words ADD COLUMN farsi_norm TEXT");

// Seed with the starter vocabulary the first time the DB is created
const seedCount = db.prepare("SELECT COUNT(*) AS c FROM words").get().c;
if (seedCount === 0) {
  const seed = db.prepare(
    "INSERT INTO words (category, english, translit, farsi, farsi_norm, added_by) VALUES (?, ?, ?, ?, ?, ?)"
  );
  const starter = [
    ["Family & baby", "mom", "maman", "مامان"],
    ["Family & baby", "dad", "baba", "بابا"],
    ["Family & baby", "my dear / sweetheart", "azizam", "عزیزم"],
    ["Family & baby", "I love you", "doostet daram", "دوستت دارم"],
    ["Family & baby", "go to sleep", "bekhab", "بخواب"],
    ["Family & baby", "come here", "bia injâ", "بیا اینجا"],
    ["Family & baby", "well done", "âfarin", "آفرین"],
    ["Family & baby", "are you hungry?", "goshnei?", "گشنه‌ای؟"],
    ["Greetings", "hello", "salâm", "سلام"],
    ["Greetings", "goodbye", "khodâhâfez", "خداحافظ"],
    ["Greetings", "thank you", "mamnoon", "ممنون"],
    ["Greetings", "good morning", "sobh bekheir", "صبح بخیر"],
    ["Numbers", "one", "yek", "یک"],
    ["Numbers", "two", "do", "دو"],
    ["Numbers", "three", "se", "سه"],
    ["Food & home", "water", "âb", "آب"],
    ["Food & home", "bread", "noon", "نون"],
    ["Food & home", "home", "khoone", "خونه"],
  ];
  const insertMany = db.transaction((rows) => {
    for (const [category, english, translit, farsi] of rows) {
      seed.run(category, english, translit, farsi, normalizeFa(farsi), "starter set");
    }
  });
  insertMany(starter);

  // Also seed the larger frequency-list-based starter vocabulary, if it
  // was built successfully at image build time (see build_starter_words.py).
  try {
    const bigListPath = "/app/models/starter_words.json";
    if (fs.existsSync(bigListPath)) {
      const bigList = JSON.parse(fs.readFileSync(bigListPath, "utf-8"));
      const insertBig = db.transaction((rows) => {
        for (const w of rows) {
          seed.run(w.category, w.english, w.translit || "", w.farsi, normalizeFa(w.farsi), "common words list");
        }
      });
      insertBig(bigList);
      console.log(`Seeded ${bigList.length} words from the common-words starter list.`);
    }
  } catch (err) {
    console.error("Failed to seed starter word list:", err.message);
  }
}

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));
app.use("/audio", express.static(AUDIO_DIR));

const TOOLS_DIR = path.join(__dirname, "tools");
const PIPER_MODEL = "/app/models/fa_IR-gyro-medium.onnx";

// Mirrors tools/fa_normalize.py. The same Persian word typed on an Arabic
// keyboard uses different characters (ي/ك) than on a Persian one (ی/ک), so
// without this a saved correction wouldn't be found next time.
const FA_CHAR_MAP = {
  "\u064A": "\u06CC", "\u0649": "\u06CC", "\u0643": "\u06A9",
  "\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627",
  "\u0671": "\u0627", "\u0629": "\u0647", "\u06C0": "\u0647",
  "\u0624": "\u0648", "\u200C": "", "\u200F": "", "\u200E": "", "\u0640": "",
};

function normalizeFa(text) {
  if (!text) return "";
  let out = "";
  for (const ch of String(text).trim()) {
    const code = ch.codePointAt(0);
    // Strip short-vowel and other diacritic marks.
    if ((code >= 0x064b && code <= 0x0652) || code === 0x0670) continue;
    out += Object.prototype.hasOwnProperty.call(FA_CHAR_MAP, ch) ? FA_CHAR_MAP[ch] : ch;
  }
  return out.trim();
}

// Store the normalized form alongside each word and index it, so looking up
// a previously-corrected word is a single indexed query rather than reading
// and normalizing the whole table on every suggestion.
db.exec("CREATE INDEX IF NOT EXISTS idx_words_farsi_norm ON words(farsi_norm)");
{
  const needsBackfill = db
    .prepare("SELECT id, farsi FROM words WHERE farsi_norm IS NULL AND farsi IS NOT NULL AND farsi != ''")
    .all();
  if (needsBackfill.length) {
    const setNorm = db.prepare("UPDATE words SET farsi_norm = ? WHERE id = ?");
    db.transaction((rows) => {
      for (const r of rows) setNorm.run(normalizeFa(r.farsi), r.id);
    })(needsBackfill);
    console.log(`Backfilled normalized spellings for ${needsBackfill.length} words.`);
  }
}

function runPython(script, text, timeoutMs = 15000) {
  return new Promise((resolve) => {
    execFile("python3", [path.join(TOOLS_DIR, script), text], { timeout: timeoutMs }, (err, stdout, stderr) => {
      if (stderr && stderr.trim()) {
        console.error(`${script} stderr:`, stderr.trim());
      }
      if (err) {
        console.error(`${script} failed:`, err.message);
        return resolve("");
      }
      resolve((stdout || "").trim());
    });
  });
}

// Calls the persistent translate_server.py process (kept loaded in memory
// by start.sh) instead of spawning a fresh Python process per request.
// Retries for a bit since that server can take several seconds to finish
// loading its model right after the container starts.
async function translateFarsi(text) {
  const url = `http://127.0.0.1:5001/translate?text=${encodeURIComponent(text)}`;
  for (let attempt = 0; attempt < 8; attempt++) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (res.ok) {
        const data = await res.json();
        return data.translation || "";
      }
    } catch (err) {
      // Translation server likely still starting up -- wait and retry.
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  console.error("Translation server did not respond after retries.");
  return "";
}

// Calls the same persistent Python server for transliteration, which now
// uses a Persian G2P neural model instead of the older espeak-ng guess.
async function transliterateFarsi(text) {
  const url = `http://127.0.0.1:5001/transliterate?text=${encodeURIComponent(text)}`;
  for (let attempt = 0; attempt < 8; attempt++) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (res.ok) {
        const data = await res.json();
        return data.translit || "";
      }
    } catch (err) {
      // Server likely still starting up -- wait and retry.
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  console.error("Transliteration server did not respond after retries.");
  return "";
}

// Generate pronunciation audio. Prefers the persistent Python server, which
// keeps the voice model loaded in memory; falls back to launching the piper
// command per word if that server isn't available.
async function generateAudio(farsiText, wordId) {
  const outPath = path.join(AUDIO_DIR, `${wordId}.wav`);
  try {
    const url =
      `http://127.0.0.1:5001/speak?text=${encodeURIComponent(farsiText)}` +
      `&out=${encodeURIComponent(outPath)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(30000) });
    if (res.ok) {
      const data = await res.json();
      if (data.ok && fs.existsSync(outPath)) return true;
    }
  } catch (err) {
    // Fall through to the slower per-word method below.
  }
  return generateAudioSubprocess(farsiText, wordId, outPath);
}

function generateAudioSubprocess(farsiText, wordId, outPath) {
  return new Promise((resolve) => {
    execFile(
      "piper",
      ["-m", PIPER_MODEL, "-f", outPath, "--", farsiText],
      { timeout: 30000 },
      (err, stdout, stderr) => {
        if (err) {
          console.error(`Piper TTS failed for word ${wordId}:`, err.message);
          if (stderr) console.error(stderr.toString());
        }
        resolve(!err && fs.existsSync(outPath));
      }
    );
  });
}

app.get("/api/words", (req, res) => {
  const rows = db.prepare("SELECT * FROM words ORDER BY category, id").all();
  res.json(rows);
});

// Given Persian script, suggest an English translation and a Finglish
// spelling. Both are just starting points -- the person adding the word
// can edit either before saving.
app.post("/api/suggest", async (req, res) => {
  const { farsi } = req.body || {};
  if (!farsi || !farsi.trim()) {
    return res.status(400).json({ error: "farsi text is required" });
  }
  const key = farsi.trim();

  // If this exact word already exists in the family's own word list (from a
  // past addition or a manual correction), reuse that answer directly
  // instead of re-asking the AI models -- this means a correction made once
  // via Manage is never re-guessed wrong again.
  const existing = db
    .prepare(
      "SELECT english, translit FROM words WHERE farsi_norm = ? AND english != '' LIMIT 1"
    )
    .get(normalizeFa(key));
  if (existing) {
    return res.json({ english: existing.english, translit: existing.translit });
  }

  const [english, translit] = await Promise.all([
    translateFarsi(key),
    transliterateFarsi(key),
  ]);
  res.json({ english, translit });
});

app.post("/api/words", async (req, res) => {
  const { category, english, translit, farsi, addedBy } = req.body || {};
  if (!category || !english || !translit) {
    return res.status(400).json({ error: "category, english, and translit are required" });
  }
  const info = db
    .prepare(
      "INSERT INTO words (category, english, translit, farsi, farsi_norm, added_by) VALUES (?, ?, ?, ?, ?, ?)"
    )
    .run(category.trim(), english.trim(), translit.trim(), (farsi || "").trim(), normalizeFa(farsi), (addedBy || "").trim());
  const wordId = info.lastInsertRowid;
  const row = db.prepare("SELECT * FROM words WHERE id = ?").get(wordId);

  // Respond straight away rather than making the person wait several seconds
  // watching a "Saving..." message. The audio appears on the card shortly
  // after; the Manage tab shows which words are still waiting for it.
  res.status(201).json(row);

  if (farsi && farsi.trim()) {
    generateAudio(farsi.trim(), wordId)
      .then((ok) => {
        if (ok) db.prepare("UPDATE words SET has_audio = 1 WHERE id = ?").run(wordId);
      })
      .catch((err) => console.error("Background audio generation failed:", err.message));
  }
});

app.put("/api/words/:id", async (req, res) => {
  const id = req.params.id;
  const existing = db.prepare("SELECT * FROM words WHERE id = ?").get(id);
  if (!existing) return res.status(404).json({ error: "not found" });
  const { category, english, translit, farsi } = req.body || {};
  if (!category || !english || !translit) {
    return res.status(400).json({ error: "category, english, and translit are required" });
  }
  db.prepare(
    "UPDATE words SET category = ?, english = ?, translit = ?, farsi = ?, farsi_norm = ? WHERE id = ?"
  ).run(category.trim(), english.trim(), translit.trim(), (farsi || "").trim(), normalizeFa(farsi), id);

  if (farsi && farsi.trim()) {
    const ok = await generateAudio(farsi.trim(), id);
    db.prepare("UPDATE words SET has_audio = ? WHERE id = ?").run(ok ? 1 : 0, id);
  } else {
    db.prepare("UPDATE words SET has_audio = 0 WHERE id = ?").run(id);
  }

  const row = db.prepare("SELECT * FROM words WHERE id = ?").get(id);
  res.json(row);
});

// Regenerate audio for a word using its already-stored Farsi text, without
// changing anything else. Used to backfill audio for the starter vocabulary
// (which was inserted directly into the database before audio generation
// existed) and to retry any word whose audio failed to generate earlier.
app.post("/api/words/:id/audio", async (req, res) => {
  const row = db.prepare("SELECT * FROM words WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "not found" });
  if (!row.farsi) return res.status(400).json({ error: "no farsi text stored for this word" });
  const ok = await generateAudio(row.farsi, row.id);
  db.prepare("UPDATE words SET has_audio = ? WHERE id = ?").run(ok ? 1 : 0, row.id);
  res.json({ has_audio: ok ? 1 : 0 });
});

app.delete("/api/words/:id", (req, res) => {
  const id = req.params.id;
  db.prepare("DELETE FROM words WHERE id = ?").run(id);
  const audioPath = path.join(AUDIO_DIR, `${id}.wav`);
  if (fs.existsSync(audioPath)) fs.unlinkSync(audioPath);
  res.status(204).end();
});

app.get("/api/categories", (req, res) => {
  const rows = db.prepare("SELECT DISTINCT category FROM words ORDER BY category").all();
  res.json(rows.map((r) => r.category));
});

const PORT = 8099;
app.listen(PORT, () => {
  console.log(`Farsi words server listening on ${PORT}`);
});

