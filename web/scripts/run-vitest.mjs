import { realpathSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { delimiter, dirname, join } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const projectDir = dirname(scriptDir)
const realProjectDir = realpathSync(projectDir)

process.chdir(realProjectDir)

const env = {
  ...process.env,
  PATH: [join(realProjectDir, 'node_modules', '.bin'), process.env.PATH ?? ''].filter(Boolean).join(delimiter),
}

const child = spawn('vitest', process.argv.slice(2), {
  cwd: realProjectDir,
  env,
  stdio: 'inherit',
  shell: true,
})

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal)
    return
  }
  process.exit(code ?? 1)
})
