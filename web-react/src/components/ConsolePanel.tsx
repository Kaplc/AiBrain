import { useEffect, useRef, useState } from 'react'
import { useRouter } from '../router'
import './ConsolePanel.css'

type LogType = 'info' | 'success' | 'warn' | 'error'

interface ConsoleLine {
  id: number
  text: string
  type: LogType
}

/* 控制台命令引擎（移植自 Vue 版 ConsoleEngine） */
class ConsoleEngine {
  private _lineId = 0
  private _commands = new Map<string, { name: string; description: string; execute: (cmd: string, ctx: any) => void }>()
  private _ctx: any = { currentPage: '', router: { push: () => {} }, reload: () => {} }
  private _logHandler: ((line: ConsoleLine) => void) | null = null

  init(ctx: any) { this._ctx = ctx }
  setLogHandler(h: (line: ConsoleLine) => void) { this._logHandler = h }

  log(text: string, type: LogType = 'info'): ConsoleLine {
    const line = { id: ++this._lineId, text, type }
    this._logHandler?.(line)
    return line
  }

  register(name: string, fn: any, description: string) {
    this._commands.set(name, { name, execute: fn, description })
  }

  getCommands() { return this._commands }

  execute(input: string) {
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

  showWelcome() {
    this.log('═══════════════════════════════', 'info')
    this.log('  AiBrain 控制台', 'success')
    this.log('═══════════════════════════════', 'info')
    this.log('输入 help 查看可用命令', 'info')
    this.log('', 'info')
  }

  registerBuiltinCommands() {
    const self = this
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

    this.register('status', () => {
      self.log('═══════════════════════════════', 'info')
      self.log('         系统状态', 'info')
      self.log('═══════════════════════════════', 'info')
      self.log(`当前页面: ${self._ctx.currentPage || 'unknown'}`, 'info')
      self.log('═══════════════════════════════', 'info')
    }, '显示系统状态')

    this.register('pages', () => {
      const pages = [
        { name: 'overview', desc: '总览' },
        { name: 'memory', desc: '记忆' },
        { name: 'chat', desc: '对话' },
        { name: 'brain', desc: '大脑' },
        { name: 'gate', desc: 'Gate' },
        { name: 'stream', desc: '流' },
        { name: 'stats', desc: '用量' },
        { name: 'logs', desc: '日志' },
        { name: 'settings', desc: '设置' },
      ]
      self.log('可用页面：', 'info')
      pages.forEach((p) => {
        const marker = p.name === self._ctx.currentPage ? ' ◄' : ''
        self.log(`  ${p.name.padEnd(10)} - ${p.desc}${marker}`, p.name === self._ctx.currentPage ? 'success' : 'info')
      })
    }, '列出所有页面')

    this.register('reload', () => {
      self.log('刷新页面...', 'info')
      self._ctx.reload()
    }, '刷新当前页面')

    this.register('open', (cmd) => {
      const page = cmd.slice(5).trim().toLowerCase()
      if (!page) {
        self.log('请指定页面名，例如: open memory', 'warn')
        return
      }
      const validPages = ['overview', 'memory', 'chat', 'brain', 'gate', 'stream', 'stats', 'logs', 'settings']
      if (!validPages.includes(page)) {
        self.log(`未知页面: ${page}`, 'error')
        return
      }
      self.log(`正在打开页面: ${page}...`, 'info')
      self._ctx.router.push('/' + page)
      self.log(`已切换到: ${page}`, 'success')
    }, '打开指定页面')

    this.register('time', () => {
      const now = new Date()
      const timeStr = now.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'long',
      })
      self.log('═══════════════════════════════', 'info')
      self.log(`  当前时间: ${timeStr}`, 'success')
      self.log('═══════════════════════════════', 'info')
    }, '显示当前日期和时间')
  }
}

const engine = new ConsoleEngine()
engine.registerBuiltinCommands()

export function ConsolePanel() {
  const [visible, setVisible] = useState(false)
  const [lines, setLines] = useState<ConsoleLine[]>([])
  const [inputValue, setInputValue] = useState('')
  const outputRef = useRef<HTMLDivElement | null>(null)
  const { path, navigate, reload } = useRouter()

  useEffect(() => {
    const toggle = () => setVisible((v) => !v)
    window.addEventListener('aibrain:toggle-console', toggle)
    return () => window.removeEventListener('aibrain:toggle-console', toggle)
  }, [])

  useEffect(() => {
    engine.init({ currentPage: path.replace(/^\//, '').split('/')[0], router: { push: navigate }, reload })
    engine.setLogHandler((line) => {
      setLines((prev) => [...prev, line])
      if (outputRef.current) {
        outputRef.current.scrollTop = outputRef.current.scrollHeight
      }
    })
  }, [path, navigate, reload])

  useEffect(() => {
    if (visible && lines.length === 0) engine.showWelcome()
  }, [visible])

  function handleSubmit() {
    const input = inputValue.trim()
    if (!input) return
    engine.execute(input)
    setInputValue('')
  }

  function handleKeydown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <>
      {visible && (
        <div className="console-wrap show">
          <div className="console-header">
            <div className="console-title">控制台</div>
            <div className="console-actions">
              <button className="btn-clear" onClick={() => setLines([])}>清空</button>
              <button className="btn-close" onClick={() => setVisible(false)}>关闭</button>
            </div>
          </div>
          <div className="console-output" ref={outputRef}>
            {lines.map((line) => (
              <div key={line.id} className={`console-line type-${line.type}`}>{line.text}</div>
            ))}
          </div>
          <div className="console-input-wrap">
            <span className="console-prompt">&gt;</span>
            <input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              className="console-input"
              placeholder="输入命令..."
              onKeyDown={handleKeydown}
              autoFocus
            />
          </div>
        </div>
      )}
      {!visible && <div className="console-hint">按 ~ 打开控制台</div>}
    </>
  )
}
