'use client';

import { useEffect, useState } from 'react';

import { addCollectionItem, deleteCollectionItem, fetchCollectionItems, updateCollectionItem } from '@/lib/api';

type CollectionItem = {
  id: number;
  card_id: number;
  purchase_price: number;
  purchase_date: string;
  quantity: number;
  estimated_value?: number;
  unrealized_pnl?: number;
};

export default function CollectionPanel() {
  const [items, setItems] = useState<CollectionItem[]>([]);
  const [cardId, setCardId] = useState('1');
  const [price, setPrice] = useState('100');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const data = await fetchCollectionItems();
    setItems(data);
    setLoading(false);
  }

  async function addItem() {
    await addCollectionItem({
      card_id: Number(cardId),
      purchase_price: Number(price),
      purchase_date: '2026-01-01',
      quantity: 1,
      is_graded: false,
    });
    await load();
  }

  async function updateItem(item: CollectionItem) {
    await updateCollectionItem(item.id, {
      card_id: item.card_id,
      purchase_price: Number(price),
      purchase_date: item.purchase_date,
      quantity: item.quantity,
      is_graded: false,
    });
    setEditingId(null);
    await load();
  }

  async function removeItem(itemId: number) {
    await deleteCollectionItem(itemId);
    await load();
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
      <h2 className="text-lg font-semibold">Collection Tracker</h2>
      <p className="mb-3 text-sm text-slate-400">Track cost basis, estimated value, and unrealized P&L.</p>
      <div className="mb-3 grid grid-cols-3 gap-2">
        <input
          className="rounded border border-slate-700 bg-slate-950 p-2"
          value={cardId}
          onChange={(e) => setCardId(e.target.value)}
          placeholder="Card ID"
        />
        <input
          className="rounded border border-slate-700 bg-slate-950 p-2"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="Purchase price"
        />
        <button className="rounded bg-green-600 px-4 font-medium" onClick={addItem}>
          Add Item
        </button>
      </div>
      {loading && <p className="text-sm text-slate-400">Loading collection…</p>}
      {!loading && items.length === 0 && <p className="text-sm text-slate-400">No collection items yet.</p>}
      <ul className="space-y-2 text-sm">
        {items.map((item) => (
          <li key={item.id} className="rounded border border-slate-700 bg-slate-950 p-3">
            <p>
              <span className="font-semibold">Card #{item.card_id}</span> · Qty {item.quantity}
            </p>
            <p className="text-slate-400">
              Cost ${item.purchase_price} · Est ${item.estimated_value} · P&L ${item.unrealized_pnl}
            </p>
            <div className="mt-2 flex gap-2">
              {editingId === item.id ? (
                <button className="rounded bg-amber-600 px-2 py-1" onClick={() => updateItem(item)}>
                  Save
                </button>
              ) : (
                <button className="rounded bg-slate-700 px-2 py-1" onClick={() => setEditingId(item.id)}>
                  Edit
                </button>
              )}
              <button className="rounded bg-red-700 px-2 py-1" onClick={() => removeItem(item.id)}>
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
