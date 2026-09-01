"use client";

import { ChevronRight, Terminal } from "lucide-react";

import { CopyableCommand } from "@/components/ui/copyable-command";

interface SnapshotRow {
  name: string;
  sub: string;
  required: "wajib" | "wajib-fitur" | "opsional";
  address: string;
}

const SNAPSHOT: SnapshotRow[] = [
  { name: "Backend", sub: "otak Krixil — chat, agent, tools", required: "wajib", address: "localhost:8000" },
  { name: "Web App", sub: "antarmuka di browser", required: "wajib", address: "localhost:3000" },
  {
    name: "host-runner",
    sub: "akses nyata ke file & command di komputer Anda",
    required: "wajib-fitur",
    address: "127.0.0.1:8002",
  },
  { name: "CLI kirxil", sub: "coding agent langsung di terminal", required: "opsional", address: "perintah kirxil" },
];

const REQUIRED_LABEL: Record<SnapshotRow["required"], string> = {
  wajib: "Wajib",
  "wajib-fitur": "Wajib untuk Code / CLI",
  opsional: "Opsional",
};

const REFERENCE: { label: string; value: string }[] = [
  { label: "Web app", value: "http://localhost:3000" },
  { label: "Dokumentasi API backend", value: "http://localhost:8000/docs" },
  {
    label: "Matikan semua backend",
    value: "docker compose -f infrastructure\\compose\\docker-compose.yml down",
  },
  {
    label: "Lihat status container",
    value: "docker compose -f infrastructure\\compose\\docker-compose.yml ps",
  },
  { label: "Login CLI ulang", value: "kirxil logout   (lalu)   kirxil login" },
  { label: "Jalankan satu goal cepat", value: 'kirxil run "goal Anda"' },
  { label: "Lihat model yang tersedia", value: "kirxil models" },
];

const FAQ: { q: string; badge?: string; body: React.ReactNode }[] = [
  {
    q: 'Web-nya "Failed to Load Page" / connection refused',
    badge: "Sering terjadi",
    body: (
      <p>
        Artinya <code className="font-mono">npm run dev</code> (Langkah 2) belum dijalankan, atau terminalnya sudah
        tertutup. Server web harus tetap menyala di terminalnya sendiri selama dipakai — buka lagi terminal baru dan
        ulangi Langkah 2.
      </p>
    ),
  },
  {
    q: '"kirxil" tidak dikenali / not recognized',
    badge: "Sering terjadi",
    body: (
      <div className="flex flex-col gap-2">
        <p>
          PATH baru berlaku di jendela terminal yang <b>baru dibuka</b> — tutup terminal yang sedang dipakai, buka
          yang baru, coba lagi.
        </p>
        <p>
          Masih belum bisa? Jalankan dengan alamat lengkapnya dulu:{" "}
          <code className="font-mono">&amp; &quot;$env:APPDATA\npm\kirxil.cmd&quot;</code>
        </p>
      </div>
    ),
  },
  {
    q: '"host-runner isn\'t reachable" di halaman Code / CLI gagal jalan',
    body: (
      <p>
        host-runner (Langkah 3) belum jalan atau terminalnya ditutup. Ini service terpisah yang harus tetap menyala
        sendiri — bukan bagian dari Backend di Langkah 1.
      </p>
    ),
  },
  {
    q: 'Docker error / "cannot connect to the Docker daemon"',
    body: (
      <p>
        Docker Desktop belum menyala. Buka aplikasinya dari Start Menu, tunggu sampai statusnya siap (ikon paus di
        system tray tidak lagi loading), baru ulangi Langkah 1.
      </p>
    ),
  },
  {
    q: "AI menjawab aneh / seperti tidak benar-benar melakukan tool call-nya",
    body: (
      <p>
        Ini keterbatasan model lokal (<code className="font-mono">llama3.1:8b</code>) yang sudah diketahui — untuk
        goal yang butuh beberapa langkah sekaligus, kadang model &quot;menceritakan&quot; langkahnya alih-alih
        benar-benar memanggil tool. Untuk goal satu-langkah biasanya lancar. Bukan bug di Krixil-nya sendiri.
      </p>
    ),
  },
];

function StepBlock({ n, title, tag, children }: { n: number; title: string; tag?: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 border-b border-border py-8 first:pt-2 last:border-b-0">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary font-mono text-sm font-semibold text-primary-foreground">
        {n}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">{title}</h2>
          {tag && (
            <span className="rounded-md border border-border bg-secondary/30 px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
              {tag}
            </span>
          )}
        </div>
        <div className="mt-3 flex flex-col gap-3">{children}</div>
      </div>
    </div>
  );
}

function Callout({ tone = "info", children }: { tone?: "info" | "warn"; children: React.ReactNode }) {
  return (
    <div
      className={
        "flex items-start gap-2 rounded-lg border p-3 text-xs " +
        (tone === "warn"
          ? "border-destructive/30 bg-destructive/5 text-destructive"
          : "border-primary/25 bg-primary/5 text-foreground")
      }
    >
      <span className="mt-0.5 shrink-0">{tone === "warn" ? "⚠" : "✓"}</span>
      <span>{children}</span>
    </div>
  );
}

export default function HelpPage() {
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
        <h1 className="text-sm font-medium">Help</h1>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-8">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-10">
          <div>
            <h2 className="text-2xl font-semibold sm:text-3xl">Menjalankan Krixil AI</h2>
            <p className="mt-2 max-w-[60ch] text-sm text-muted-foreground">
              Tiga bagian yang perlu dinyalakan, urutannya, dan cara mengakses masing-masing — dari nol sampai bisa
              mengetik goal pertama Anda, di web maupun di terminal.
            </p>
          </div>

          {/* Snapshot */}
          <div className="overflow-hidden rounded-xl border border-border">
            <div className="border-b border-border bg-secondary/20 px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Apa saja yang ada
            </div>
            <div className="divide-y divide-border">
              {SNAPSHOT.map((row) => (
                <div key={row.name} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                  <div>
                    <p className="font-medium">{row.name}</p>
                    <p className="text-xs text-muted-foreground">{row.sub}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={
                        "rounded-full px-2.5 py-0.5 text-[11px] font-medium " +
                        (row.required === "opsional"
                          ? "bg-secondary/40 text-muted-foreground"
                          : "bg-primary/10 text-primary")
                      }
                    >
                      {REQUIRED_LABEL[row.required]}
                    </span>
                    <span className="font-mono text-xs text-muted-foreground">{row.address}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Steps */}
          <div>
            <StepBlock n={1} title="Nyalakan Backend" tag="Docker Desktop harus jalan dulu">
              <p className="text-sm text-muted-foreground">
                Buka aplikasi <b className="text-foreground">Docker Desktop</b> di Windows, tunggu sampai ikonnya
                tidak loading. Baru setelah itu jalankan ini di PowerShell:
              </p>
              <CopyableCommand
                command={
                  "cd D:\\Krixil\n\n" +
                  '$envFile = "--env-file", "services\\ai-service\\.env"\n' +
                  "docker compose $envFile -f infrastructure\\compose\\docker-compose.yml up -d\n\n" +
                  "docker compose $envFile -f infrastructure\\compose\\docker-compose.yml exec api alembic upgrade head"
                }
              />
              <Callout>
                Cek sudah jalan: buka <b>localhost:8000/docs</b> di browser, kalau muncul halaman dokumentasi API
                berarti sudah aktif.
              </Callout>
            </StepBlock>

            <StepBlock n={2} title="Nyalakan Web App">
              <p className="text-sm text-muted-foreground">
                Terminal <b className="text-foreground">baru</b> (biarkan yang tadi tetap terbuka), lalu:
              </p>
              <CopyableCommand command={"cd D:\\Krixil\\apps\\web\nnpm run dev"} />
              <Callout>
                Biarkan jendela terminal ini tetap terbuka selama dipakai. Tutup terminalnya = web-nya ikut mati.
                Buka <b>localhost:3000</b> di browser.
              </Callout>
            </StepBlock>

            <StepBlock n={3} title="Nyalakan host-runner" tag="opsional — untuk Code & CLI">
              <p className="text-sm text-muted-foreground">
                Hanya perlu ini kalau mau pakai halaman <b className="text-foreground">Code</b> di web (yang butuh
                akses nyata ke D:\) atau CLI <span className="font-mono">kirxil</span>. Terminal baru lagi:
              </p>
              <CopyableCommand
                command={
                  "cd D:\\Krixil\\services\\host-runner\n" +
                  ".venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002"
                }
              />
              <Callout tone="warn">
                Ini memberi akses <b>nyata, tanpa sandbox</b> ke drive <span className="font-mono">D:\</span> Anda —
                AI bisa baca/tulis/hapus file dan menjalankan command apa pun di sana. Belum pernah setup venv-nya?
                Lihat <span className="font-mono">services/host-runner/README.md</span>.
              </Callout>
            </StepBlock>

            <StepBlock n={4} title="Pakai CLI kirxil" tag="opsional — dari terminal mana pun">
              <p className="text-sm text-muted-foreground">
                Setelah Backend (langkah 1) dan host-runner (langkah 3) jalan, buka terminal <b className="text-foreground">baru</b> —
                bisa dari folder mana saja:
              </p>
              <CopyableCommand command="kirxil login" />
              <p className="text-xs text-muted-foreground">
                Diminta: workspace slug, email, password, dan <span className="font-mono">HOST_ROOT</span> — ketik{" "}
                <span className="font-mono">D:\</span>.
              </p>
              <CopyableCommand command={"cd D:\\folder-project-Anda\nkirxil"} />
              <Callout>
                Langsung masuk mode tanya-jawab. <span className="font-mono">Ctrl+C</span> = hentikan proses yang
                jalan. <span className="font-mono">/model</span> = ganti model.{" "}
                <span className="font-mono">/exit</span> = keluar.
              </Callout>
            </StepBlock>
          </div>

          {/* Quick reference */}
          <div>
            <h2 className="text-base font-semibold">Referensi cepat</h2>
            <p className="mt-1 text-sm text-muted-foreground">Kalau sudah pernah setup dan cuma lupa alamat/perintahnya.</p>
            <div className="mt-3 overflow-hidden rounded-xl border border-border">
              <table className="w-full text-sm">
                <tbody className="divide-y divide-border">
                  {REFERENCE.map((row) => (
                    <tr key={row.label}>
                      <td className="w-1/3 px-4 py-2.5 text-muted-foreground">{row.label}</td>
                      <td className="px-4 py-2.5">
                        <code className="rounded border border-border bg-secondary/30 px-1.5 py-0.5 font-mono text-xs break-all">
                          {row.value}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* FAQ */}
          <div className="pb-4">
            <h2 className="text-base font-semibold">Kalau ada masalah</h2>
            <div className="mt-3 flex flex-col gap-2">
              {FAQ.map((item) => (
                <FaqItem key={item.q} q={item.q} badge={item.badge}>
                  {item.body}
                </FaqItem>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 border-t border-border pt-6 pb-2 text-xs text-muted-foreground">
            <Terminal className="size-3.5" />
            Detail lengkap komponen &amp; keputusan desain: lihat <span className="font-mono">docs/architecture/</span>{" "}
            di repo.
          </div>
        </div>
      </div>
    </div>
  );
}

function FaqItem({ q, badge, children }: { q: string; badge?: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-lg border border-border">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium marker:content-none">
        {badge && (
          <span className="shrink-0 rounded-md bg-destructive/10 px-1.5 py-0.5 font-mono text-[10px] text-destructive">
            {badge}
          </span>
        )}
        <span className="min-w-0 flex-1">{q}</span>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
      </summary>
      <div className="px-4 pb-4 text-sm text-muted-foreground">{children}</div>
    </details>
  );
}
