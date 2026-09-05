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

// Seed with the starter vocabulary the first time the DB is created
const seedCount = db.prepare("SELECT COUNT(*) AS c FROM words").get().c;
if (seedCount === 0) {
  const seed = db.prepare(
    "INSERT INTO words (category, english, translit, farsi, added_by) VALUES (?, ?, ?, ?, ?)"
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
      seed.run(category, english, translit, farsi, "starter set");
    }
  });
  insertMany(starter);
}

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));
app.use("/audio", express.static(AUDIO_DIR));

const TOOLS_DIR = path.join(__dirname, "tools");
const PIPER_MODEL = "/app/models/fa_IR-gyro-medium.onnx";

function runPython(script, text) {
  return new Promise((resolve) => {
    execFile("python3", [path.join(TOOLS_DIR, script), text], { timeout: 15000 }, (err, stdout) => {
      if (err) return resolve("");
      resolve((stdout || "").trim());
    });
  });
}

function generateAudio(farsiText, wordId) {
  return new Promise((resolve) => {
    const outPath = path.join(AUDIO_DIR, `${wordId}.wav`);
    const piper = execFile(
      "piper",
      ["--model", PIPER_MODEL, "--output_file", outPath],
      { timeout: 20000 },
      (err) => {
        resolve(!err && fs.existsSync(outPath));
      }
    );
    piper.stdin.write(farsiText);
    piper.stdin.end();
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
  const [english, translit] = await Promise.all([
    runPython("translate.py", farsi.trim()),
    runPython("transliterate.py", farsi.trim()),
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
      "INSERT INTO words (category, english, translit, farsi, added_by) VALUES (?, ?, ?, ?, ?)"
    )
    .run(category.trim(), english.trim(), translit.trim(), (farsi || "").trim(), (addedBy || "").trim());
  const wordId = info.lastInsertRowid;

  if (farsi && farsi.trim()) {
    const ok = await generateAudio(farsi.trim(), wordId);
    if (ok) {
      db.prepare("UPDATE words SET has_audio = 1 WHERE id = ?").run(wordId);
    }
  }

  const row = db.prepare("SELECT * FROM words WHERE id = ?").get(wordId);
  res.status(201).json(row);
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

