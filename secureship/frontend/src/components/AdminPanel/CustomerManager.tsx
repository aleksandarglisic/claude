import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useListCustomersAdminCustomersGet,
  useCreateCustomerAdminCustomersPost,
  useUpdateCustomerAdminCustomersCustomerIdPut,
  useDeleteCustomerAdminCustomersCustomerIdDelete,
  getListCustomersAdminCustomersGetQueryKey,
} from '../../api/generated/admin/admin'
import type { CustomerResponse, CustomerCreate } from '../../api/generated/secureShipAPI.schemas'
import styles from './Manager.module.css'

type FormData = { first_name: string; last_name: string; phone_number: string; address: string }
const emptyForm: FormData = { first_name: '', last_name: '', phone_number: '', address: '' }

export default function CustomerManager() {
  const qc = useQueryClient()
  const { data: customers = [], isLoading } = useListCustomersAdminCustomersGet()

  const [mode, setMode] = useState<'list' | 'create' | 'edit'>('list')
  const [editTarget, setEditTarget] = useState<CustomerResponse | null>(null)
  const [form, setForm] = useState<FormData>(emptyForm)
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: getListCustomersAdminCustomersGetQueryKey() })

  const createMutation = useCreateCustomerAdminCustomersPost({
    mutation: {
      onSuccess: () => { invalidate(); reset() },
      onError: () => setError('Failed to create customer.'),
    },
  })

  const updateMutation = useUpdateCustomerAdminCustomersCustomerIdPut({
    mutation: {
      onSuccess: () => { invalidate(); reset() },
      onError: () => setError('Failed to update customer.'),
    },
  })

  const deleteMutation = useDeleteCustomerAdminCustomersCustomerIdDelete({
    mutation: {
      onSuccess: () => { invalidate(); setConfirmDelete(null) },
      onError: () => setError('Failed to delete customer.'),
    },
  })

  const reset = () => { setMode('list'); setEditTarget(null); setForm(emptyForm); setError('') }

  const openCreate = () => { setForm(emptyForm); setError(''); setMode('create') }
  const openEdit = (c: CustomerResponse) => {
    setEditTarget(c)
    setForm({ first_name: c.first_name, last_name: c.last_name, phone_number: c.phone_number, address: c.address })
    setError('')
    setMode('edit')
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (mode === 'create') {
      createMutation.mutate({ data: form as CustomerCreate })
    } else if (mode === 'edit' && editTarget) {
      updateMutation.mutate({ customerId: editTarget.id, data: form })
    }
  }

  const pending = createMutation.isPending || updateMutation.isPending

  return (
    <div className={styles.section}>
      <div className={styles.toolbar}>
        <h2 className={styles.title}>Customers</h2>
        {mode === 'list' && (
          <button className={styles.btnPrimary} onClick={openCreate}>+ New Customer</button>
        )}
        {mode !== 'list' && (
          <button className={styles.btnGhost} onClick={reset}>Cancel</button>
        )}
      </div>

      {mode !== 'list' && (
        <form className={styles.form} onSubmit={handleSubmit}>
          <h3 className={styles.formTitle}>{mode === 'create' ? 'New Customer' : 'Edit Customer'}</h3>
          {error && <p className={styles.errorMsg}>{error}</p>}
          <div className={styles.formGrid}>
            <label className={styles.label}>
              First name
              <input className={styles.input} value={form.first_name} required
                onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} />
            </label>
            <label className={styles.label}>
              Last name
              <input className={styles.input} value={form.last_name} required
                onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} />
            </label>
            <label className={styles.label}>
              Phone (E.164)
              <input className={styles.input} value={form.phone_number} required
                onChange={e => setForm(f => ({ ...f, phone_number: e.target.value }))} />
            </label>
            <label className={`${styles.label} ${styles.spanFull}`}>
              Address
              <input className={styles.input} value={form.address} required
                onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
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
              <th>Name</th>
              <th>Phone</th>
              <th>Address</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {customers.length === 0 && (
              <tr><td colSpan={4} className={styles.empty}>No customers yet.</td></tr>
            )}
            {customers.map(c => (
              <tr key={c.id} className={confirmDelete === c.id ? styles.rowDanger : ''}>
                <td>{c.first_name} {c.last_name}</td>
                <td>{c.phone_number}</td>
                <td>{c.address}</td>
                <td className={styles.actions}>
                  {confirmDelete === c.id ? (
                    <>
                      <span className={styles.confirmText}>Delete?</span>
                      <button className={styles.btnDanger}
                        onClick={() => deleteMutation.mutate({ customerId: c.id })}
                        disabled={deleteMutation.isPending}>
                        Yes, delete
                      </button>
                      <button className={styles.btnGhost} onClick={() => setConfirmDelete(null)}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <button className={styles.btnGhost} onClick={() => openEdit(c)}>Edit</button>
                      <button className={styles.btnDanger} onClick={() => setConfirmDelete(c.id)}>Delete</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
