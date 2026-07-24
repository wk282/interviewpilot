const DRAFT_PREFIX = 'interviewpilot:answer-draft'

function draftKey(scopeId: string, questionId: string) {
  return `${DRAFT_PREFIX}:${scopeId}:${questionId}`
}

export function readInterviewAnswerDraft(scopeId: string, questionId: string) {
  try {
    return sessionStorage.getItem(draftKey(scopeId, questionId)) ?? ''
  } catch {
    return ''
  }
}

export function saveInterviewAnswerDraft(
  scopeId: string,
  questionId: string,
  content: string,
) {
  try {
    const key = draftKey(scopeId, questionId)
    if (content) sessionStorage.setItem(key, content)
    else sessionStorage.removeItem(key)
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export function removeInterviewAnswerDraft(scopeId: string, questionId: string) {
  try {
    sessionStorage.removeItem(draftKey(scopeId, questionId))
  } catch {
    // No cleanup is required when storage is unavailable.
  }
}

export function removeInterviewAnswerDrafts(scopeId: string) {
  try {
    const prefix = `${DRAFT_PREFIX}:${scopeId}:`
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index)
      if (key?.startsWith(prefix)) sessionStorage.removeItem(key)
    }
  } catch {
    // No cleanup is required when storage is unavailable.
  }
}
