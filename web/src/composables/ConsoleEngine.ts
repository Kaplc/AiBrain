/* 控制台命令引擎 - 面向对象设计 */

export type LogType = 'info' | 'success' | 'warn' | 'error'

export interface ConsoleLine {
  id: number
  text: string
  type: LogType
  timestamp: Date
}

export interface Command {
  name: string
  description: string
  execute: (cmd: string, ctx: ConsoleContext) => void
}

export interface ConsoleContext {
  currentPage: string
  router: { push: (path: string) => void }
  reload: () => void
}

export interface LogHandler {
  (line: ConsoleLine): void
}

export class ConsoleEngine {
  private _lineId = 0
  private _commands = new Map<string, Command>()
  private _ctx: ConsoleContext = {
    currentPage: '',
    router: { push: () => {} },
    reload: () => {},
  }
  private _logHandler: LogHandler | null = null

  // ── 上下文 ──────────────────────────────────────────────
  init(ctx: ConsoleContext): void {
    this._ctx = ctx
  }

  setLogHandler(handler: LogHandler): void {
    this._logHandler = handler
  }

  // ── 日志输出 ─────────────────────────────────────────────
  log(text: string, type: LogType = 'info'): ConsoleLine {
    const line: ConsoleLine = {
      id: ++this._lineId,
      text,
      type,
      timestamp: new Date(),
    }
    this._logHandler?.(line)
    return line
  }

  // ── 命令注册 ──────────────────────────────────────────────
  register(name: string, fn: Command['execute'], description: string): void {
    this._commands.set(name, { name, execute: fn, description })
  }

  getCommands(): Map<string, Command> {
    return this._commands
  }

  // ── 命令执行 ──────────────────────────────────────────────
  execute(input: string): void {
    const trimmed = input.trim()
    if (!trimmed) return

    this.log('> ' + trimmed, 'info')

    const parts = trimmed.split(/\s+/)
    const cmdName = parts[0].toLowerCase()
    const cmd = this._commands.get(cmdName)

    if (!cmd) {
      this.log(`未知命令: ${cmdName}，输入 help 查看可用命令`, 'error')
      return
    }

    try {
      cmd.execute(trimmed, this._ctx)
    } catch (e: any) {
      this.log(`命令执行错误: ${e.message || e}`, 'error')
    }
  }

  // ── 欢迎信息 ──────────────────────────────────────────────
  showWelcome(): void {
    this.log('═══════════════════════════════', 'info')
    this.log('  AiBrain 控制台', 'success')
    this.log('═══════════════════════════════', 'info')
    this.log('输入 help 查看可用命令', 'info')
    this.log('', 'info')
  }

  // ── 初始化内置命令 ────────────────────────────────────────
  registerBuiltinCommands(): void {
    const self = this

    // help
    this.register('help', () => {
      self.log('═══════════════════════════════', 'info')
      self.log('       可用命令', 'info')
      self.log('═══════════════════════════════', 'info')
      self._commands.forEach((cmd, name) => {
        if (name === 'help') return
        self.log(`  ${name.padEnd(12)} - ${cmd.description}`, 'info')
      })
      self.log('═══════════════════════════════', 'info')
    }, '显示帮助信息')

    // status
    this.register('status', () => {
      self.log('═══════════════════════════════', 'info')
      self.log('         系统状态', 'info')
      self.log('═══════════════════════════════', 'info')
      self.log(`当前页面: ${self._ctx.currentPage || 'unknown'}`, 'info')
      self.log('═══════════════════════════════', 'info')
    }, '显示系统状态')

    // pages
    this.register('pages', () => {
      const pages = [
        { name: 'overview', desc: '总览' },
        { name: 'memory', desc: '记忆' },
        { name: 'stream', desc: '流' },
        { name: 'wiki', desc: 'Wiki' },
        { name: 'logs', desc: '日志' },
        { name: 'settings', desc: '设置' },
      ]
      self.log('可用页面：', 'info')
      pages.forEach(p => {
        const marker = p.name === self._ctx.currentPage ? ' ◄' : ''
        self.log(`  ${p.name.padEnd(10)} - ${p.desc}${marker}`, p.name === self._ctx.currentPage ? 'success' : 'info')
      })
    }, '列出所有页面')

    // reload
    this.register('reload', () => {
      self.log('刷新页面...', 'info')
      self._ctx.reload()
      self.log('刷新完成', 'success')
    }, '刷新当前页面')

    // open <page>
    this.register('open', (cmd) => {
      const page = cmd.slice(5).trim().toLowerCase()
      if (!page) {
        self.log('请指定页面名，例如: open memory', 'warn')
        self.log('使用 pages 命令查看可用页面', 'info')
        return
      }
      const validPages = ['overview', 'memory', 'stream', 'wiki', 'logs', 'settings']
      if (!validPages.includes(page)) {
        self.log(`未知页面: ${page}`, 'error')
        self.log('使用 pages 命令查看可用页面', 'info')
        return
      }
      self.log(`正在打开页面: ${page}...`, 'info')
      self._ctx.router.push('/' + page)
      self.log(`已切换到: ${page}`, 'success')
    }, '打开指定页面')

    // time
    this.register('time', () => {
      const now = new Date()
      const timeStr = now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        weekday: 'long',
      })
      self.log('═══════════════════════════════', 'info')
      self.log(`  当前时间: ${timeStr}`, 'success')
      self.log('═══════════════════════════════', 'info')
    }, '显示当前日期和时间')
  }
}

// 单例导出
export const consoleEngine = new ConsoleEngine()
consoleEngine.registerBuiltinCommands()
