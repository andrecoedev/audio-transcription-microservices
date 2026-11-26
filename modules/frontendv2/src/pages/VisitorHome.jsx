import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import './visitor-home.css'

const RETURN_TO_DEMO = '/login?returnTo=%2Fnew-transcription'
const prefersReducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

const conversation = [
  ['0:00–0:15', 'Falante 1', 'Vamos organizar a apresentação do nosso projeto fictício. Precisamos mostrar o objetivo, um exemplo e os próximos passos.'],
  ['0:15–0:30', 'Falante 2', 'Concordo. Proponho começar pelo exemplo, mas ainda podemos discutir a ordem dos slides.'],
  ['0:30–0:45', 'Falante 1', 'Decidimos que a apresentação terá três partes: objetivo, exemplo e próximos passos. A ordem dos slides será definida depois.'],
  ['0:45–1:00', 'Falante 2', 'Eu, Falante 2, vou preparar o exemplo até sexta-feira.'],
  ['1:00–1:15', 'Falante 1', 'Também precisamos revisar os slides. Essa tarefa está confirmada, mas ainda não definimos responsável nem prazo.'],
  ['1:15–1:30', 'Falante 2', 'Fica em aberto qual será a ordem dos slides. Vamos discutir isso na próxima conversa.'],
]

const evidence = [
  { type: 'Tópico', text: 'Organização da apresentação do projeto fictício.', quote: 0, label: 'Trecho 1' },
  { type: 'Decisão', text: 'A apresentação terá três partes: objetivo, exemplo e próximos passos.', quote: 2, label: 'Trecho 3' },
  { type: 'Tarefas', tasks: [
    ['Preparar o exemplo da apresentação.', 'Responsável: Falante 2 · Prazo: sexta-feira'],
    ['Revisar os slides.', 'Responsável: Não identificado · Prazo: Sem prazo explícito'],
  ], quote: 3, label: 'Trechos 4 e 5' },
  { type: 'Pergunta em aberto', text: 'Qual será a ordem dos slides?', quote: 5, label: 'Trecho 6' },
]

const formats = [
  ['TXT', 'Texto corrido, para ler, revisar ou colar em outro documento.'],
  ['SRT', 'Legenda com tempo de cada trecho, para vídeo.'],
  ['VTT', 'Legenda no formato da web, com os mesmos tempos.'],
  ['JSON', 'Trechos, tempos e falantes estruturados, para integrar.'],
]

function useLandingMotion(evidenceRef) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const reduced = prefersReducedMotion()
    const revealNodes = document.querySelectorAll('.visitor-home [data-reveal]')
    if (!reduced && 'IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      }), { threshold: 0.12 })
      revealNodes.forEach((node) => observer.observe(node))
      return () => observer.disconnect()
    }
    revealNodes.forEach((node) => node.classList.add('is-visible'))
    if (reduced) setStep(4)
    return undefined
  }, [])

  useEffect(() => {
    const section = evidenceRef.current
    if (!section || prefersReducedMotion()) return undefined
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const rect = section.getBoundingClientRect()
        const span = Math.max(1, section.offsetHeight - window.innerHeight)
        const progress = Math.max(0, Math.min(0.999, -rect.top / span))
        setStep(Math.floor(progress * 4))
      })
    }
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    update()
    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
      cancelAnimationFrame(frame)
    }
  }, [evidenceRef])
  return step
}

export default function VisitorHome() {
  const evidenceRef = useRef(null)
  const step = useLandingMotion(evidenceRef)
  return <div className="visitor-home" id="visitor-home">
    <header className="vh-header">
      <Link className="vh-brand" to="/" aria-label="USAGI — Início"><strong>USAGI</strong><span lang="ja">うさぎ</span></Link>
      <Link className="vh-login" to={RETURN_TO_DEMO}>Entrar</Link>
    </header>
    <div className="vh-content">
      <section className="vh-scene vh-hero" aria-labelledby="vh-title">
        <div className="vh-hero-copy">
          <p className="vh-kicker" data-reveal>Transcrição · Compreensão de reuniões</p>
          <h1 id="vh-title" data-reveal>O que foi dito vira o que fazer.</h1>
          <p className="vh-lead" data-reveal>A USAGI transcreve sua reunião, separa quem falou e organiza decisões, tarefas e perguntas em aberto — cada item com o trecho que o comprova.</p>
          <div className="vh-actions" data-reveal>
            <Link className="vh-button vh-button-primary" to="/new-transcription">Ver demonstração</Link>
            <span className="vh-note">Dados de exemplo. Nenhum áudio seu é enviado.</span>
          </div>
        </div>
        <figure className="vh-paper" data-reveal aria-label="Trecho da reunião de exemplo">
          <figcaption className="vh-kicker">Reunião de exemplo · 0:30</figcaption>
          <p className="vh-paper-quote">“Decidimos que a apresentação terá <mark>três partes</mark>: objetivo, exemplo e próximos passos.”</p>
          <p className="vh-paper-speaker">Falante 1</p>
          <span className="vh-stamp" aria-hidden="true">決定</span>
          <p className="vh-paper-item"><span className="vh-kicker">Decisão</span>A apresentação terá três partes.</p>
        </figure>
      </section>

      <section className="vh-scene vh-conversation" aria-labelledby="vh-conversation-title">
        <header className="vh-section-heading" data-reveal>
          <p className="vh-kicker">Reunião de exemplo · 1:30</p>
          <h2 id="vh-conversation-title">Primeiro, a conversa inteira em texto.</h2>
        </header>
        <ol className="vh-dialogue">
          {conversation.map(([time, speaker, text], index) => <li className={`vh-utterance ${index % 2 ? 'vh-speaker-two' : ''}`} key={time} data-reveal>
            <time>{time}</time><b>{speaker}</b><p>{text}</p>
          </li>)}
        </ol>
      </section>

      <section className="vh-scene vh-speakers" aria-labelledby="vh-speakers-title">
        <div className="vh-speakers-copy" data-reveal>
          <h2 id="vh-speakers-title">Cada fala tem dono e tem tempo.</h2>
          <p>Com a detecção de falantes, a transcrição marca quem disse cada trecho, com início e fim.</p>
        </div>
        <dl className="vh-numbers" data-reveal>
          <div><dt>segundos de reunião</dt><dd>90</dd></div>
          <div><dt>trechos com início e fim</dt><dd>6</dd></div>
          <div><dt>falantes identificados</dt><dd>2</dd></div>
        </dl>
        <div className="vh-timeline" role="img" aria-label="Linha do tempo: seis trechos de 15 segundos alternando Falante 1 e Falante 2">
          {conversation.map((_, index) => <span className={index % 2 ? 'vh-segment-two' : ''} key={index} />)}
        </div>
        <p className="vh-timeline-caption"><i />Falante 1 <i className="vh-dot-two" />Falante 2 <span><time>0:00</time><time>1:30</time></span></p>
      </section>

      <section ref={evidenceRef} className="vh-scene vh-evidence-scene" aria-labelledby="vh-evidence-title">
        <div className="vh-evidence-stage">
          <div className="vh-evidence-grid" data-step={step}>
            <header className="vh-section-heading">
              <p className="vh-kicker">Resumo inteligente</p>
              <h2 id="vh-evidence-title">Depois, o que importa — e de onde veio.</h2>
            </header>
            <ol className="vh-transcript" aria-label="Transcrição">
              {conversation.map(([time, , text], index) => <li key={time} className={evidence.some((item) => item.quote === index) ? 'has-evidence' : ''}>
                <time>{time.split('–')[0]}</time><p>{text}</p>
              </li>)}
            </ol>
            <div className="vh-insights" aria-label="Itens identificados na conversa">
              {evidence.map((item, index) => <article className="vh-insight" data-insight={index} key={item.type}>
                <p className="vh-kicker">{item.type}</p>
                {item.text && <p className="vh-insight-text">{item.text}</p>}
                {item.tasks && <ul>{item.tasks.map(([task, details]) => <li key={task}><span aria-hidden="true" />{task}<small>{details}</small></li>)}</ul>}
                <p className="vh-citation">↖ {item.label}</p>
              </article>)}
            </div>
          </div>
        </div>
      </section>

      <section className="vh-scene vh-privacy" aria-labelledby="vh-privacy-title">
        <p className="vh-privacy-mark" lang="ja" aria-hidden="true">うさぎ</p>
        <div className="vh-privacy-copy" data-reveal>
          <p className="vh-kicker">Sobre o seu áudio</p>
          <h2 id="vh-privacy-title">O áudio é removido da USAGI após o processamento.</h2>
          <p>Ao usar transcrição externa, o áudio necessário ao processamento é enviado ao serviço selecionado, inclusive com sua própria chave. Falhas de limpeza podem deixar a remoção pendente.</p>
        </div>
      </section>

      <section className="vh-scene vh-exports" aria-labelledby="vh-exports-title">
        <div className="vh-export-inner">
          <header className="vh-section-heading" data-reveal><p className="vh-kicker">Exportação</p><h2 id="vh-exports-title">Leve para onde precisar.</h2></header>
          <div className="vh-format-window">
            <div className="vh-format-track">
              {formats.map(([name, description]) => <article className="vh-format" key={name}><p className="vh-format-name">{name}</p><p>{description}</p></article>)}
              <article className="vh-format vh-format-start"><p className="vh-kicker">Para começar</p><p className="vh-format-name"><span>100</span> MB · <span>10</span> min</p><p>Por arquivo de áudio. MP3, WAV, MP4, MPEG, M4A, FLAC, OGG e OPUS.</p></article>
            </div>
          </div>
        </div>
      </section>

      <section className="vh-scene vh-close" aria-labelledby="vh-close-title">
        <div className="vh-close-copy">
          <h2 id="vh-close-title" data-reveal>Veja uma reunião virar decisões e tarefas.</h2>
          <p data-reveal>A demonstração usa dados de exemplo e não processa nenhum áudio.</p>
          <div className="vh-close-actions" data-reveal>
            <Link className="vh-button vh-button-light" to="/new-transcription">Ver demonstração</Link>
            <Link className="vh-close-login" to={RETURN_TO_DEMO}>Já tenho conta — entrar</Link>
          </div>
        </div>
        <footer className="vh-footer"><Link className="vh-brand" to="/" aria-label="USAGI — Início"><strong>USAGI</strong><span lang="ja">うさぎ</span></Link><span>Transcrição · Compreensão de reuniões</span></footer>
      </section>
    </div>
  </div>
}
