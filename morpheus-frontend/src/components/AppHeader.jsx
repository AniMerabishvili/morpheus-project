function AppHeader({ title, meta, actions = [] }) {
  return (
    <header className="pointer-events-none absolute left-0 top-0 z-30 w-full border-b border-[#1f1f1f] bg-[#0f0f0f]/80 px-5 py-4 backdrop-blur-md">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-1 text-xs font-black uppercase tracking-[0.22em] text-[#8A7129]">
            Morpheus
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-[#E6DFA9] sm:text-4xl">
            {title}
          </h1>
        </div>
        <div className="pointer-events-auto flex flex-col gap-3 sm:items-end">
          {meta ? <p className="text-sm font-bold text-[#8A7129]">{meta}</p> : null}
          {actions.length ? (
            <div className="flex flex-wrap gap-3">
              {actions.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={action.onClick}
                  className={
                    action.variant === 'primary'
                      ? 'rounded-xl border border-[#FFDE6E] bg-[#FFDE6E] px-4 py-2 font-black text-[#0f0f0f] transition hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]'
                      : 'rounded-xl border border-[#8A7129] bg-[#141414] px-4 py-2 font-black text-[#FFDE6E] transition hover:border-[#FFDE6E] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]'
                  }
                >
                  {action.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  )
}

export default AppHeader
