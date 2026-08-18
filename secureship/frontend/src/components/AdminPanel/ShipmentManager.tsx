import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useListShipmentsAdminShipmentsGet,
  useCreateShipmentAdminShipmentsPost,
  useUpdateShipmentAdminShipmentsShipmentIdPut,
  useDeleteShipmentAdminShipmentsShipmentIdDelete,
  useListCustomersAdminCustomersGet,
  useCreatePackageAdminPackagesPost,
  useDeletePackageAdminPackagesPackageIdDelete,
  getListShipmentsAdminShipmentsGetQueryKey,
} from '../../api/generated/admin/admin'
import type { ShipmentResponse, ShipmentCreate, ShipmentStatus } from '../../api/generated/secureShipAPI.schemas'
import styles from './Manager.module.css'

const STATUSES: ShipmentStatus[] = ['label_created', 'in_transit', 'out_for_delivery', 'delivered', 'exception']

const STATUS_LABELS: Record<ShipmentStatus, string> = {
  label_created: 'Label Created',
  in_transit: 'In Transit',
  out_for_delivery: 'Out for Delivery',
  delivered: 'Delivered',
  exception: 'Exception',
}

type ShipmentForm = {
  customer_id: string
  tracking_number: string
  status: ShipmentStatus
  carrier: string
  origin: string
  destination: string
  estimated_delivery: string
}

const emptyShipmentForm: ShipmentForm = {
  customer_id: '', tracking_number: '', status: 'in_transit',
  carrier: '', origin: '', destination: '', estimated_delivery: '',
}

type PackageForm = { description: string; weight_kg: string; declared_value: string }

export default function ShipmentManager() {
  const qc = useQueryClient()
  const { data: shipments = [], isLoading } = useListShipmentsAdminShipmentsGet()
  const { data: customers = [] } = useListCustomersAdminCustomersGet()

  const [mode, setMode] = useState<'list' | 'create' | 'edit'>('list')
  const [editTarget, setEditTarget] = useState<ShipmentResponse | null>(null)
  const [form, setForm] = useState<ShipmentForm>(emptyShipmentForm)
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [pkgForms, setPkgForms] = useState<Record<string, PackageForm>>({})
  const [addingPkg, setAddingPkg] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: getListShipmentsAdminShipmentsGetQueryKey() })

  const createMutation = useCreateShipmentAdminShipmentsPost({
    mutation: {
      onSuccess: () => { invalidate(); reset() },
      onError: () => setError('Failed to create shipment.'),
    },
  })

  const updateMutation = useUpdateShipmentAdminShipmentsShipmentIdPut({
    mutation: {
      onSuccess: () => { invalidate(); reset() },
      onError: () => setError('Failed to update shipment.'),
    },
  })

  const deleteMutation = useDeleteShipmentAdminShipmentsShipmentIdDelete({
    mutation: {
      onSuccess: () => { invalidate(); setConfirmDelete(null) },
      onError: () => setError('Failed to delete shipment.'),
    },
  })

  const createPkgMutation = useCreatePackageAdminPackagesPost({
    mutation: {
      onSuccess: () => { invalidate(); setAddingPkg(null) },
    },
  })

  const deletePkgMutation = useDeletePackageAdminPackagesPackageIdDelete({
    mutation: { onSuccess: () => invalidate() },
  })

  const reset = () => { setMode('list'); setEditTarget(null); setForm(emptyShipmentForm); setError('') }

  const openCreate = () => {
    setForm({ ...emptyShipmentForm, customer_id: customers[0]?.id ?? '' })
    setError('')
    setMode('create')
  }

  const openEdit = (s: ShipmentResponse) => {
    setEditTarget(s)
    setForm({
      customer_id: s.customer_id,
      tracking_number: s.tracking_number,
      status: s.status,
      carrier: s.carrier,
      origin: s.origin,
      destination: s.destination,
      estimated_delivery: s.estimated_delivery,
    })
    setError('')
    setMode('edit')
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (mode === 'create') {
      createMutation.mutate({ data: form as ShipmentCreate })
    } else if (mode === 'edit' && editTarget) {
      updateMutation.mutate({ shipmentId: editTarget.id, data: form })
    }
  }

  const handleAddPackage = (shipmentId: string) => {
    const f = pkgForms[shipmentId]
    if (!f) return
    createPkgMutation.mutate({
      data: {
        shipment_id: shipmentId,
        description: f.description,
        weight_kg: parseFloat(f.weight_kg),
        declared_value: parseFloat(f.declared_value),
      },
    })
  }

  const pending = createMutation.isPending || updateMutation.isPending
  const customerMap = Object.fromEntries(customers.map(c => [c.id, `${c.first_name} ${c.last_name}`]))

  return (
    <div className={styles.section}>
      <div className={styles.toolbar}>
        <h2 className={styles.title}>Shipments</h2>
        {mode === 'list' && (
          <button className={styles.btnPrimary} onClick={openCreate}>+ New Shipment</button>
        )}
        {mode !== 'list' && (
          <button className={styles.btnGhost} onClick={reset}>Cancel</button>
        )}
      </div>

      {mode !== 'list' && (
        <form className={styles.form} onSubmit={handleSubmit}>
          <h3 className={styles.formTitle}>{mode === 'create' ? 'New Shipment' : 'Edit Shipment'}</h3>
          {error && <p className={styles.errorMsg}>{error}</p>}
          <div className={styles.formGrid}>
            <label className={styles.label}>
              Customer
              <select className={styles.input} value={form.customer_id} required
                onChange={e => setForm(f => ({ ...f, customer_id: e.target.value }))}>
                <option value="">Select…</option>
                {customers.map(c => (
                  <option key={c.id} value={c.id}>{c.first_name} {c.last_name}</option>
                ))}
              </select>
            </label>
            <label className={styles.label}>
              Tracking number
              <input className={styles.input} value={form.tracking_number} required
                onChange={e => setForm(f => ({ ...f, tracking_number: e.target.value }))} />
            </label>
            <label className={styles.label}>
              Status
              <select className={styles.input} value={form.status}
                onChange={e => setForm(f => ({ ...f, status: e.target.value as ShipmentStatus }))}>
                {STATUSES.map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
              </select>
            </label>
            <label className={styles.label}>
              Carrier
              <input className={styles.input} value={form.carrier} required
                onChange={e => setForm(f => ({ ...f, carrier: e.target.value }))} />
            </label>
            <label className={styles.label}>
              Origin
              <input className={styles.input} value={form.origin} required
                onChange={e => setForm(f => ({ ...f, origin: e.target.value }))} />
            </label>
            <label className={styles.label}>
              Destination
              <input className={styles.input} value={form.destination} required
                onChange={e => setForm(f => ({ ...f, destination: e.target.value }))} />
            </label>
            <label className={styles.label}>
              Est. delivery
              <input className={styles.input} type="date" value={form.estimated_delivery} required
                onChange={e => setForm(f => ({ ...f, estimated_delivery: e.target.value }))} />
            </label>
          </div>
          <div className={styles.formActions}>
            <button type="submit" className={styles.btnPrimary} disabled={pending}>
              {pending ? 'Saving…' : mode === 'create' ? 'Create' : 'Save changes'}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <p className={styles.loading}>Loading…</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th></th>
              <th>Tracking #</th>
              <th>Customer</th>
              <th>Status</th>
              <th>Carrier</th>
              <th>Route</th>
              <th>Est. Delivery</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {shipments.length === 0 && (
              <tr><td colSpan={8} className={styles.empty}>No shipments yet.</td></tr>
            )}
            {shipments.map(s => (
              <>
                <tr key={s.id} className={confirmDelete === s.id ? styles.rowDanger : ''}>
                  <td>
                    <button className={styles.expandBtn}
                      onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
                      {expanded === s.id ? '▾' : '▸'}
                    </button>
                  </td>
                  <td className={styles.mono}>{s.tracking_number}</td>
                  <td>{customerMap[s.customer_id] ?? s.customer_id}</td>
                  <td><span className={`${styles.badge} ${styles[`status_${s.status}`]}`}>{STATUS_LABELS[s.status]}</span></td>
                  <td>{s.carrier}</td>
                  <td className={styles.route}>{s.origin} → {s.destination}</td>
                  <td>{s.estimated_delivery}</td>
                  <td className={styles.actions}>
                    {confirmDelete === s.id ? (
                      <>
                        <span className={styles.confirmText}>Delete?</span>
                        <button className={styles.btnDanger}
                          onClick={() => deleteMutation.mutate({ shipmentId: s.id })}
                          disabled={deleteMutation.isPending}>
                          Yes
                        </button>
                        <button className={styles.btnGhost} onClick={() => setConfirmDelete(null)}>No</button>
                      </>
                    ) : (
                      <>
                        <button className={styles.btnGhost} onClick={() => openEdit(s)}>Edit</button>
                        <button className={styles.btnDanger} onClick={() => setConfirmDelete(s.id)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
                {expanded === s.id && (
                  <tr key={`${s.id}-pkg`} className={styles.pkgRow}>
                    <td colSpan={8}>
                      <div className={styles.pkgPanel}>
                        <strong>Packages</strong>
                        {(s.packages ?? []).length === 0 && <span className={styles.pkgEmpty}> — none</span>}
                        <table className={styles.pkgTable}>
                          <tbody>
                            {(s.packages ?? []).map(p => (
                              <tr key={p.id}>
                                <td>{p.description}</td>
                                <td>{p.weight_kg} kg</td>
                                <td>${p.declared_value}</td>
                                <td>
                                  <button className={styles.btnDanger}
                                    onClick={() => deletePkgMutation.mutate({ packageId: p.id })}>
                                    Remove
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>

                        {addingPkg === s.id ? (
                          <div className={styles.pkgForm}>
                            <input className={styles.input} placeholder="Description"
                              value={pkgForms[s.id]?.description ?? ''}
                              onChange={e => setPkgForms(f => ({ ...f, [s.id]: { ...f[s.id], description: e.target.value } }))} />
                            <input className={styles.input} placeholder="Weight (kg)" type="number" step="0.01"
                              value={pkgForms[s.id]?.weight_kg ?? ''}
                              onChange={e => setPkgForms(f => ({ ...f, [s.id]: { ...f[s.id], weight_kg: e.target.value } }))} />
                            <input className={styles.input} placeholder="Declared value ($)" type="number" step="0.01"
                              value={pkgForms[s.id]?.declared_value ?? ''}
                              onChange={e => setPkgForms(f => ({ ...f, [s.id]: { ...f[s.id], declared_value: e.target.value } }))} />
                            <button className={styles.btnPrimary} onClick={() => handleAddPackage(s.id)}
                              disabled={createPkgMutation.isPending}>
                              Add
                            </button>
                            <button className={styles.btnGhost} onClick={() => setAddingPkg(null)}>Cancel</button>
                          </div>
                        ) : (
                          <button className={styles.btnGhost} onClick={() => {
                            setPkgForms(f => ({ ...f, [s.id]: { description: '', weight_kg: '', declared_value: '' } }))
                            setAddingPkg(s.id)
                          }}>+ Add package</button>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
