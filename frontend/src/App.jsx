import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowDownUp,
  Building2,
  Car,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Factory,
  FileCheck2,
  Flag,
  Hotel,
  Lock,
  Plane,
  RefreshCcw,
  Save,
  Search,
  ShieldCheck,
  TrainFront,
  XCircle,
  Zap,
} from 'lucide-react';
import {
  getActivities,
  getActivity,
  getBatches,
  patchActivity,
  reviewActivity,
} from './api';

const SOURCE_OPTIONS = ['ALL', 'SAP', 'UTILITY', 'TRAVEL'];
const STATUS_OPTIONS = ['ALL', 'pending_review', 'approved', 'rejected', 'locked'];
const CONFIDENCE_OPTIONS = ['ALL', 'high', 'medium', 'low'];
const SCOPE_OPTIONS = ['ALL', '1', '2', '3'];

const sourceMeta = {
  SAP: { label: 'SAP', icon: Factory, tone: 'sap' },
  UTILITY: { label: 'Utility', icon: Zap, tone: 'utility' },
  TRAVEL: { label: 'Travel', icon: Plane, tone: 'travel' },
};

const activityIcons = {
  FUEL: Factory,
  ELECTRICITY: Zap,
  FLIGHT: Plane,
  HOTEL: Hotel,
  CAR_RENTAL: Car,
  RAIL: TrainFront,
};

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (Number.isNaN(number)) return value;
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(number);
}

function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
  }).format(new Date(`${value}T00:00:00`));
}

function titleize(value) {
  if (!value) return '—';
  return value
    .toString()
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function hasFlags(activity) {
  return activity?.flags && Object.keys(activity.flags).length > 0;
}

function statusTone(status) {
  if (status === 'approved') return 'good';
  if (status === 'locked') return 'locked';
  if (status === 'rejected') return 'bad';
  return 'pending';
}

function sourceLabel(source) {
  return sourceMeta[source]?.label || source;
}

function App() {
  const [batches, setBatches] = useState([]);
  const [activities, setActivities] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({
    source_type: 'ALL',
    status: 'ALL',
    confidence: 'ALL',
    scope: 'ALL',
    suspiciousOnly: false,
    query: '',
  });
  const [detailTab, setDetailTab] = useState('details');
  const [editForm, setEditForm] = useState({
    normalized_quantity: '',
    normalized_unit: '',
    co2e_kg: '',
    confidence: 'high',
    reason: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function loadData(preferredId = selectedId) {
    setError('');
    setLoading(true);
    try {
      const apiFilters = {
        source_type: filters.source_type === 'ALL' ? '' : filters.source_type,
        status: filters.status === 'ALL' ? '' : filters.status,
        confidence: filters.confidence === 'ALL' ? '' : filters.confidence,
        scope: filters.scope === 'ALL' ? '' : filters.scope,
      };
      const [batchPayload, activityPayload] = await Promise.all([
        getBatches(),
        getActivities(apiFilters),
      ]);
      setBatches(batchPayload);
      setActivities(activityPayload);
      const nextId =
        preferredId && activityPayload.some((activity) => activity.id === preferredId)
          ? preferredId
          : activityPayload[0]?.id || null;
      setSelectedId(nextId);
      if (nextId) {
        const detail = await getActivity(nextId);
        setSelected(detail);
      } else {
        setSelected(null);
      }
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [filters.source_type, filters.status, filters.confidence, filters.scope]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    getActivity(selectedId)
      .then((detail) => {
        if (active) setSelected(detail);
      })
      .catch((detailError) => setError(detailError.message));
    return () => {
      active = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!selected) return;
    setEditForm({
      normalized_quantity: selected.normalized_quantity || '',
      normalized_unit: selected.normalized_unit || '',
      co2e_kg: selected.co2e_kg || '',
      confidence: selected.confidence || 'high',
      reason: '',
    });
  }, [selected?.id]);

  const visibleActivities = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    return activities.filter((activity) => {
      if (filters.suspiciousOnly && !hasFlags(activity)) return false;
      if (!query) return true;
      const haystack = [
        activity.source_type,
        activity.activity_type,
        activity.status,
        activity.confidence,
        activity.batch_filename,
        JSON.stringify(activity.details || {}),
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [activities, filters.query, filters.suspiciousOnly]);

  useEffect(() => {
    if (loading) return;
    if (!visibleActivities.length) {
      setSelectedId(null);
      setSelected(null);
      return;
    }
    if (!visibleActivities.some((activity) => activity.id === selectedId)) {
      setSelectedId(visibleActivities[0].id);
    }
  }, [loading, selectedId, visibleActivities]);

  const summary = useMemo(() => {
    const totalCo2e = activities.reduce((sum, activity) => sum + Number(activity.co2e_kg || 0), 0);
    const sourceCount = new Set(batches.map((batch) => batch.source_type)).size;
    const scopeCount = new Set(activities.map((activity) => activity.scope)).size;
    return {
      totalRows: activities.length,
      visibleRows: visibleActivities.length,
      totalCo2e,
      pending: activities.filter((activity) => activity.status === 'pending_review').length,
      approved: activities.filter((activity) => activity.status === 'approved').length,
      locked: activities.filter((activity) => activity.status === 'locked').length,
      suspicious: activities.filter(hasFlags).length,
      failed: batches.reduce((sum, batch) => sum + Number(batch.failed_record_count || 0), 0),
      reviewed: activities.filter((activity) => ['approved', 'locked'].includes(activity.status)).length,
      sourceCount,
      scopeCount: sourceCount === 3 ? 3 : scopeCount,
    };
  }, [activities, visibleActivities, batches]);

  async function selectActivity(id) {
    setSelectedId(id);
    setDetailTab('details');
  }

  async function runReviewAction(action) {
    if (!selected) return;
    setSaving(true);
    setError('');
    try {
      await reviewActivity(selected.id, action, editForm.reason);
      await loadData(selected.id);
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setSaving(false);
    }
  }

  async function saveEdits() {
    if (!selected) return;
    setSaving(true);
    setError('');
    try {
      await patchActivity(selected.id, {
        normalized_quantity: editForm.normalized_quantity || null,
        normalized_unit: editForm.normalized_unit,
        co2e_kg: editForm.co2e_kg || null,
        confidence: editForm.confidence,
        reason: editForm.reason,
      });
      await loadData(selected.id);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  const selectedLocked = selected?.status === 'locked' || Boolean(selected?.locked_at);
  const selectedApproved = selected?.status === 'approved';

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <ShieldCheck size={22} />
          </div>
          <div>
            <p className="eyebrow">Breathe ESG</p>
            <h1>Analyst Review</h1>
            <p className="topbar-subtitle">Scope 1/2/3 review queue</p>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="org-chip">
            <Building2 size={16} />
            Demo Enterprise Client
          </span>
          <button className="icon-button" type="button" onClick={() => loadData()} title="Refresh data">
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      {error && (
        <div className="alert-banner" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      <section className="metrics-strip" aria-label="Review metrics">
        <Metric label="Rows" value={summary.totalRows} icon={Database} />
        <Metric label="CO2e kg" value={formatNumber(summary.totalCo2e, 1)} icon={ArrowDownUp} />
        <Metric label="Pending" value={summary.pending} icon={ClipboardCheck} />
        <Metric label="Reviewed" value={summary.reviewed} icon={CheckCircle2} tone="good" />
        <Metric label="Suspicious" value={summary.suspicious} icon={Flag} tone="warn" />
        <Metric label="Failed" value={summary.failed} icon={XCircle} tone="bad" />
        <Metric label="Locked" value={summary.locked} icon={Lock} tone="good" />
      </section>

      <section className="workspace-grid">
        <aside className="side-panel" aria-label="Import batches">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">Imports</p>
              <h2>Batches</h2>
            </div>
            <FileCheck2 size={20} />
          </div>
          <div className="batch-list">
            {batches.map((batch) => (
              <BatchRow key={batch.id} batch={batch} />
            ))}
          </div>
        </aside>

        <section className="main-panel">
          <div className="filters-bar">
            <div className="search-wrap">
              <Search size={16} />
              <input
                type="search"
                value={filters.query}
                onChange={(event) => setFilters((prev) => ({ ...prev, query: event.target.value }))}
                placeholder="Search source, status, material, trip"
                aria-label="Search rows"
              />
            </div>
            <Segmented
              label="Source"
              options={SOURCE_OPTIONS}
              value={filters.source_type}
              onChange={(value) => setFilters((prev) => ({ ...prev, source_type: value }))}
              formatter={(value) => (value === 'ALL' ? 'All' : sourceLabel(value))}
            />
            <Segmented
              label="Status"
              options={STATUS_OPTIONS}
              value={filters.status}
              onChange={(value) => setFilters((prev) => ({ ...prev, status: value }))}
              formatter={(value) => (value === 'ALL' ? 'All' : titleize(value))}
            />
            <Segmented
              label="Scope"
              options={SCOPE_OPTIONS}
              value={filters.scope}
              onChange={(value) => setFilters((prev) => ({ ...prev, scope: value }))}
              formatter={(value) => (value === 'ALL' ? 'All' : `S${value}`)}
            />
            <button
              type="button"
              className={`toggle-button ${filters.suspiciousOnly ? 'active' : ''}`}
              onClick={() => setFilters((prev) => ({ ...prev, suspiciousOnly: !prev.suspiciousOnly }))}
            >
              <Flag size={15} />
              Flagged
            </button>
          </div>

          <div className="table-head">
            <div>
              <p className="section-kicker">Activity rows</p>
              <h2>{summary.visibleRows} visible</h2>
            </div>
            <Segmented
              label="Confidence"
              options={CONFIDENCE_OPTIONS}
              value={filters.confidence}
              onChange={(value) => setFilters((prev) => ({ ...prev, confidence: value }))}
              formatter={(value) => (value === 'ALL' ? 'All confidence' : titleize(value))}
            />
          </div>

          <ActivityTable
            activities={visibleActivities}
            selectedId={selectedId}
            loading={loading}
            onSelect={selectActivity}
          />
        </section>

        <aside className="detail-panel" aria-label="Selected activity detail">
          {selected ? (
            <>
              <div className="detail-header">
                <SourcePill source={selected.source_type} />
                <Badge tone={statusTone(selected.status)}>{titleize(selected.status)}</Badge>
              </div>
              <div className="detail-title">
                <ActivityGlyph activityType={selected.activity_type} />
                <div>
                  <h2>{titleize(selected.activity_type)}</h2>
                  <p>
                    {formatDate(selected.activity_start_date)}
                    {selected.activity_end_date && selected.activity_end_date !== selected.activity_start_date
                      ? ` - ${formatDate(selected.activity_end_date)}`
                      : ''}
                  </p>
                </div>
              </div>

              <div className="review-actions">
                <button
                  type="button"
                  className="action-button good"
                  disabled={saving || selectedLocked}
                  onClick={() => runReviewAction('approve')}
                >
                  <CheckCircle2 size={16} />
                  Approve
                </button>
                <button
                  type="button"
                  className="action-button bad"
                  disabled={saving || selectedLocked}
                  onClick={() => runReviewAction('reject')}
                >
                  <XCircle size={16} />
                  Reject
                </button>
                <button
                  type="button"
                  className="action-button locked"
                  disabled={saving || selectedLocked || !selectedApproved}
                  onClick={() => runReviewAction('lock')}
                >
                  <Lock size={16} />
                  Lock
                </button>
              </div>

              <label className="reason-field">
                <span>Review note</span>
                <input
                  value={editForm.reason}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, reason: event.target.value }))}
                  placeholder="Optional note"
                />
              </label>

              <div className="edit-grid">
                <label>
                  <span>Normalized quantity</span>
                  <input
                    value={editForm.normalized_quantity}
                    disabled={selectedLocked}
                    onChange={(event) =>
                      setEditForm((prev) => ({ ...prev, normalized_quantity: event.target.value }))
                    }
                  />
                </label>
                <label>
                  <span>Unit</span>
                  <input
                    value={editForm.normalized_unit}
                    disabled={selectedLocked}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, normalized_unit: event.target.value }))}
                  />
                </label>
                <label>
                  <span>CO2e kg</span>
                  <input
                    value={editForm.co2e_kg}
                    disabled={selectedLocked}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, co2e_kg: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Confidence</span>
                  <select
                    value={editForm.confidence}
                    disabled={selectedLocked}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, confidence: event.target.value }))}
                  >
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </label>
              </div>

              <button
                type="button"
                className="save-button"
                disabled={saving || selectedLocked}
                onClick={saveEdits}
              >
                <Save size={16} />
                Save edits
              </button>

              <div className="detail-tabs" role="tablist" aria-label="Activity detail">
                {['details', 'raw', 'audit'].map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={detailTab === tab}
                    className={detailTab === tab ? 'active' : ''}
                    onClick={() => setDetailTab(tab)}
                  >
                    {titleize(tab)}
                  </button>
                ))}
              </div>

              <div className="detail-body-scroll">
                <DetailBody selected={selected} detailTab={detailTab} />
              </div>
              <div className="detail-status">
                <span>Source trace</span>
                <strong>{selected.raw_source_record?.source_record_key || selected.raw_record}</strong>
              </div>
            </>
          ) : (
            <div className="empty-detail">
              <Database size={24} />
              <p>No activity selected</p>
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}

function Metric({ label, value, icon: Icon, tone = '' }) {
  return (
    <div className={`metric ${tone}`}>
      <Icon size={19} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function Segmented({ label, options, value, onChange, formatter }) {
  return (
    <div className="segmented" aria-label={label}>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className={value === option ? 'active' : ''}
          onClick={() => onChange(option)}
        >
          {formatter ? formatter(option) : option}
        </button>
      ))}
    </div>
  );
}

function BatchRow({ batch }) {
  const MetaIcon = sourceMeta[batch.source_type]?.icon || Database;
  const warnings = Number(batch.warning_record_count || 0);
  const failed = Number(batch.failed_record_count || 0);
  return (
    <article className="batch-row">
      <div className={`batch-icon ${sourceMeta[batch.source_type]?.tone || ''}`}>
        <MetaIcon size={18} />
      </div>
      <div className="batch-content">
        <div className="batch-title">
          <strong>{sourceLabel(batch.source_type)}</strong>
          <Badge tone={failed ? 'bad' : warnings ? 'warn' : 'good'}>{titleize(batch.status)}</Badge>
        </div>
        <p title={batch.original_filename}>{batch.original_filename}</p>
        <div className="batch-stats">
          <span>{batch.raw_record_count} raw</span>
          <span>{batch.activity_count} normalized</span>
          <span>{warnings} flagged</span>
        </div>
      </div>
    </article>
  );
}

function ActivityTable({ activities, selectedId, loading, onSelect }) {
  if (loading) {
    return (
      <div className="table-state">
        <RefreshCcw size={20} />
        <span>Loading rows</span>
      </div>
    );
  }

  if (!activities.length) {
    return (
      <div className="table-state">
        <Search size={20} />
        <span>No matching rows</span>
      </div>
    );
  }

  return (
    <div className="activity-table-wrap">
      <table className="activity-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Activity</th>
            <th>Period</th>
            <th>Raw</th>
            <th>Normalized</th>
            <th>CO2e kg</th>
            <th>Flags</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {activities.map((activity) => (
            <tr
              key={activity.id}
              className={selectedId === activity.id ? 'selected' : ''}
              onClick={() => onSelect(activity.id)}
            >
              <td>
                <SourcePill source={activity.source_type} />
              </td>
              <td>
                <div className="activity-cell">
                  <ActivityGlyph activityType={activity.activity_type} />
                  <span>{titleize(activity.activity_type)}</span>
                </div>
              </td>
              <td>{formatDate(activity.activity_start_date)}</td>
              <td>
                {formatNumber(activity.raw_quantity, 1)} {activity.raw_unit}
              </td>
              <td>
                {formatNumber(activity.normalized_quantity, 1)} {activity.normalized_unit}
              </td>
              <td>{formatNumber(activity.co2e_kg, 1)}</td>
              <td>
                {hasFlags(activity) ? (
                  <Badge tone="warn">{Object.keys(activity.flags).length}</Badge>
                ) : (
                  <Badge tone="good">0</Badge>
                )}
              </td>
              <td>
                <Badge tone={statusTone(activity.status)}>{titleize(activity.status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourcePill({ source }) {
  const meta = sourceMeta[source] || sourceMeta.SAP;
  const Icon = meta.icon;
  return (
    <span className={`source-pill ${meta.tone}`}>
      <Icon size={14} />
      {meta.label}
    </span>
  );
}

function ActivityGlyph({ activityType }) {
  const Icon = activityIcons[activityType] || Database;
  return (
    <span className="activity-glyph" aria-hidden="true">
      <Icon size={16} />
    </span>
  );
}

function Badge({ children, tone = '' }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function DetailBody({ selected, detailTab }) {
  if (detailTab === 'raw') {
    return <JsonBlock value={selected.raw_source_record?.raw_payload || {}} />;
  }

  if (detailTab === 'audit') {
    return (
      <div className="audit-list">
        {selected.audit_events?.length ? (
          selected.audit_events.map((event) => (
            <article className="audit-event" key={event.id}>
              <div>
                <Badge tone={event.action === 'created' ? 'pending' : statusTone(event.action)}>
                  {titleize(event.action)}
                </Badge>
                <time>{new Date(event.created_at).toLocaleString()}</time>
              </div>
              {event.reason && <p>{event.reason}</p>}
            </article>
          ))
        ) : (
          <div className="table-state compact">No audit events</div>
        )}
      </div>
    );
  }

  return (
    <div className="detail-facts">
      <Fact label="Factor" value={selected.emission_factor_key || '—'} />
      <Fact label="Factor value" value={`${selected.emission_factor_value || '—'} ${selected.emission_factor_unit || ''}`} />
      <Fact label="Batch" value={selected.batch_filename} />
      <Fact label="Confidence" value={titleize(selected.confidence)} />
      <div className="flags-box">
        <strong>Flags</strong>
        {hasFlags(selected) ? <JsonBlock value={selected.flags} dense /> : <span>None</span>}
      </div>
      <JsonBlock value={selected.details || {}} dense />
    </div>
  );
}

function Fact({ label, value }) {
  return (
    <div className="fact-row">
      <span>{label}</span>
      <strong title={value}>{value}</strong>
    </div>
  );
}

function JsonBlock({ value, dense = false }) {
  return (
    <pre className={`json-block ${dense ? 'dense' : ''}`}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export default App;
