import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const PAGE_SIZE = 10;

const Categories = () => {
  const { t, translateData } = useI18n();
  const [categories, setCategories] = useState([]);
  const [page, setPage] = useState(1);
  const navigate = useNavigate();

  useEffect(() => {
    api.get('/categories')
      .then((res) => setCategories(Array.isArray(res.data) ? res.data : []))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    setPage(1);
  }, [categories.length]);

  const getIcon = (name) => {
    const n = name.toLowerCase();
    if (n.includes('imprim')) return 'fa-print';
    if (n.includes('proj')) return 'fa-video';
    if (n.includes('scan')) return 'fa-qrcode';
    if (n.includes('ecran') || n.includes('screen')) return 'fa-display';
    if (n.includes('reseau') || n.includes('network') || n.includes('wifi')) return 'fa-wifi';
    if (n.includes('acces') || n.includes('access') || n.includes('controle')) return 'fa-door-open';
    return 'fa-cube';
  };

  const totalPages = Math.max(1, Math.ceil(categories.length / PAGE_SIZE));

  const pagedCategories = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return categories.slice(start, start + PAGE_SIZE);
  }, [categories, page]);

  return (
    <main className="page-pad categories-page">
      <div className="container">
        <header className="catalog-head">
          <h1 className="catalog-title">{t('categories.title')}</h1>
          <p className="catalog-subtitle">{t('categories.subtitle')}</p>
        </header>

        {categories.length === 0 ? (
          <div className="card" style={{ padding: '18px', color: 'var(--muted)' }}>
            {t('categories.noData')}
          </div>
        ) : (
          <>
            <section className="catalog-grid">
              {pagedCategories.map((cat, i) => (
                <article
                  key={`${cat.nom}-${i}`}
                  className="catalog-card card"
                  onClick={() => navigate(`/search?type=${encodeURIComponent(cat.nom)}`)}
                >
                  <div className="catalog-ico"><i className={`fa-solid ${getIcon(cat.nom)}`} /></div>
                  <h3 className="catalog-name">{translateData('type', cat.nom)}</h3>
                  <p className="catalog-count">{cat.count ?? 0} {t('categories.devices')}</p>
                </article>
              ))}
            </section>

            {totalPages > 1 && (
              <div className="pagination">
                <button className="btn pagination-btn" disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                  {t('common.previous')}
                </button>
                <span className="pagination-info">{t('common.page')} {page} / {totalPages}</span>
                <button className="btn pagination-btn" disabled={page === totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
                  {t('common.next')}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
};

export default Categories;
