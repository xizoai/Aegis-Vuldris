import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, projectApi } from '../api/client'
import type { Project } from '../api/types'
import { Alert, ConfirmDialog, EmptyState, Field, Loading, PageHeader } from '../components/Primitives'
import { FolderIcon, PlusIcon, SearchIcon, TrashIcon } from '../components/icons'
import { formatDate, shortId } from '../lib/format'

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('')
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setProjects(await projectApi.list())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load projects.')
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    void load()
  }, [load])

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setCreating(true)
    setError(null)
    try {
      await projectApi.create({ name, description: description || null })
      setName('')
      setDescription('')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create project.')
    } finally {
      setCreating(false)
    }
  }

  async function handleDeleteConfirmed() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await projectApi.remove(pendingDelete.id)
      setPendingDelete(null)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete project.')
    } finally {
      setDeleting(false)
    }
  }

  const visibleProjects = useMemo(() => {
    const query = filter.trim().toLowerCase()
    if (!query) return projects
    return projects.filter(
      (project) =>
        project.name.toLowerCase().includes(query) ||
        (project.description ?? '').toLowerCase().includes(query),
    )
  }, [projects, filter])

  return (
    <section>
      <PageHeader
        eyebrow="Workspace"
        title="Projects"
        subtitle="A project groups targets, security tests, executions, findings, and reports."
        actions={
          projects.length > 0 ? (
            <span className="count-chip">
              {projects.length} {projects.length === 1 ? 'project' : 'projects'}
            </span>
          ) : undefined
        }
      />

      {error && <Alert kind="error">{error}</Alert>}

      <div className="split-layout">
        <div>
          {!loading && projects.length > 0 && (
            <div className="card">
              <div className="card-header">
                <h2>Your projects</h2>
                <label className="search-field" htmlFor="project-filter">
                  <SearchIcon size={15} />
                  <input
                    id="project-filter"
                    type="search"
                    placeholder="Filter projects…"
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                  />
                </label>
              </div>

              {visibleProjects.length === 0 ? (
                <EmptyState icon={<SearchIcon size={18} />}>
                  No project matches “{filter}”.
                </EmptyState>
              ) : (
                <ul className="card-list">
                  {visibleProjects.map((project) => (
                    <li key={project.id} className="card project-card">
                      <div className="card-body">
                        <h3>
                          <FolderIcon size={16} />
                          {project.name}
                        </h3>
                        {project.description && <p>{project.description}</p>}
                        <p className="meta-line">
                          Created {formatDate(project.created_at)} · ID{' '}
                          <code className="mono">{shortId(project.id)}</code>
                        </p>
                      </div>
                      <div className="card-actions">
                        <Link className="btn btn-secondary btn-sm" to={`/projects/${project.id}`}>
                          Open
                        </Link>
                        <button
                          type="button"
                          className="danger icon-label sm"
                          onClick={() => setPendingDelete(project)}
                        >
                          <TrashIcon size={14} />
                          Delete
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {loading && (
            <div className="card">
              <Loading label="Loading projects…" />
            </div>
          )}

          {!loading && projects.length === 0 && (
            <EmptyState icon={<FolderIcon size={18} />}>
              No projects yet. Create your first project to get started.
            </EmptyState>
          )}
        </div>

        <div className="split-side">
          <form className="card create-form" onSubmit={handleCreate}>
            <div className="card-header">
              <h2>
                <PlusIcon size={16} />
                New project
              </h2>
            </div>
            <p className="card-note">
              Name the assessment. You will add targets, load the attack library, and run
              tests inside it.
            </p>
            <Field label="Name" htmlFor="project-name">
              <input
                id="project-name"
                name="name"
                required
                maxLength={200}
                placeholder="Customer support chatbot"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field label="Description" htmlFor="project-description">
              <textarea
                id="project-description"
                name="description"
                rows={3}
                maxLength={1000}
                placeholder="What is being assessed, and for whom?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </Field>
            <button type="submit" disabled={creating || name.trim() === ''}>
              {creating ? 'Creating…' : 'Create project'}
            </button>
          </form>
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete project"
        message={
          <p>
            Delete <strong>{pendingDelete?.name}</strong>? This also removes its targets,
            tests, executions, findings, and reports. This cannot be undone.
          </p>
        }
        busy={deleting}
        onConfirm={() => void handleDeleteConfirmed()}
        onCancel={() => setPendingDelete(null)}
      />
    </section>
  )
}
