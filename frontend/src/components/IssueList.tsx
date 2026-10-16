import type { Category, Severity } from '../api'

export function SeverityTag({ severity }: { severity: Severity }) {
  return (
    <span className="severity">
      <span className={`severity-dot ${severity}`} aria-hidden="true" />
      {severity}
    </span>
  )
}

export function IssueList({ category }: { category: Category }) {
  return (
    <div>
      {category.issues.length === 0 && <p className="empty">No issues found in this category. 🎉</p>}
      {category.issues.map((issue, index) => (
        <details className="issue" key={issue.id} open={index === 0 && issue.severity === 'critical'}>
          <summary>
            <SeverityTag severity={issue.severity} />
            <span className="issue-title">{issue.title}</span>
            {issue.count > 1 && <span className="issue-count">× {issue.count}</span>}
          </summary>
          <div className="issue-body">
            <p>{issue.description}</p>
            <div className="fix">
              <strong>How to fix: </strong>
              {issue.recommendation}
            </div>
            {issue.examples.length > 0 && (
              <ul className="examples" aria-label="Examples">
                {issue.examples.map((example) => (
                  <li key={example}>{example}</li>
                ))}
              </ul>
            )}
          </div>
        </details>
      ))}
      {category.passed.length > 0 && (
        <ul className="passed-list" aria-label="Passed checks">
          {category.passed.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
