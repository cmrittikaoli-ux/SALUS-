/** Public "About the doctor" block, shared by the booking page and the doctor's own profile editor. */
export default function DoctorProfile({ profile }) {
  if (!profile) return <p className="muted">This doctor hasn’t written a profile yet.</p>
  const facts = [
    ['Experience', profile.years_experience != null ? `${profile.years_experience} years, since ${profile.practising_since}` : null],
    ['Qualifications', profile.qualifications?.join(', ')],
    ['Languages', profile.languages?.join(', ')],
    ['Also consults at', profile.hospital],
    ['Registration', profile.registration_no],
  ].filter(([, v]) => v)

  return (
    <div className="stack">
      {profile.bio && <p style={{ maxWidth: '62ch' }}>{profile.bio}</p>}
      {facts.length > 0 && (
        <dl className="facts">
          {facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      )}
      {profile.services?.length > 0 && (
        <div className="row" style={{ gap: 6 }}>
          {profile.services.map((s) => <span key={s} className="chip scheduled">{s}</span>)}
        </div>
      )}
    </div>
  )
}
