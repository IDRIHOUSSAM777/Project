import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const PAGE_SIZE = 10;

const parseBackendDate = (value) => {
  if (!value) return null;
  const dateString = String(value);

  // FastAPI may send naive UTC datetime (without timezone). Force UTC parsing in that case.
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(dateString);
  const parsed = new Date(hasTimezone ? dateString : `${dateString}Z`);

  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
};

const formatRelativeTime = (value, t, locale) => {
  const parsed = parseBackendDate(value);
  if (!parsed) return t('history.unknownDate');

  const diffMs = Date.now() - parsed.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });

  if (diffMs < minute) return rtf.format(0, 'second');
  if (diffMs < hour) return rtf.format(-Math.floor(diffMs / minute), 'minute');
  if (diffMs < day) return rtf.format(-Math.floor(diffMs / hour), 'hour');
  return rtf.format(-Math.floor(diffMs / day), 'day');
};

const formatActionDate = (value, t, locale) => {
  const parsed = parseBackendDate(value);
  if (!parsed) return t('history.unknownDate');

  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
};

const statusClass = (status) => {
  const normalized = String(status || '').toUpperCase();
  return normalized === 'ACTIVE' || normalized === 'WAITING'
    ? 'history-status-progress'
    : 'history-status-done';
};

const History = () => {
  const { t, translateData, locale } = useI18n();
  const [history, setHistory] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [actionsPage, setActionsPage] = useState(1);
  const [searchPage, setSearchPage] = useState(1);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([api.get('/users/me/history'), api.get('/users/me/reservations')])
      .then(([h, r]) => {
        setHistory(Array.isArray(h.data) ? h.data : []);
        setReservations(Array.isArray(r.data) ? r.data : []);
      })
      .catch(() => {
        setHistory([]);
        setReservations([]);
      });
  }, []);

  useEffect(() => {
    setActionsPage(1);
  }, [reservations.length]);

  useEffect(() => {
    setSearchPage(1);
  }, [history.length]);

  const actionsTotalPages = Math.max(1, Math.ceil(reservations.length / PAGE_SIZE));
  const searchTotalPages = Math.max(1, Math.ceil(history.length / PAGE_SIZE));

  const pagedReservations = useMemo(() => {
    const start = (actionsPage - 1) * PAGE_SIZE;
    return reservations.slice(start, start + PAGE_SIZE);
  }, [reservations, actionsPage]);

  const pagedHistory = useMemo(() => {
    const start = (searchPage - 1) * PAGE_SIZE;
    return history.slice(start, start + PAGE_SIZE);
  }, [history, searchPage]);

  return (
    <main className="page-pad history-page">
      <div className="container">
        <header className="history-head">
          <h1 className="history-title">{t('history.title')}</h1>
          <p className="history-subtitle">{t('history.subtitle')}</p>
        </header>

        <section className="history-panel card">
          <div className="history-panel-head">
            <h2><i className="fa-solid fa-wave-square" /> {t('history.recentActions')}</h2>
          </div>
          <div className="history-panel-body">
            {reservations.length === 0 && <div className="history-empty">{t('history.noRecentActions')}</div>}

            {pagedReservations.map((r, i) => {
              const status = String(r.statut_reservation || '').toUpperCase();
              const iconName = status === 'ACTIVE' ? 'fa-rotate-right' : (status === 'WAITING' ? 'fa-hourglass-half' : 'fa-circle-check');

              return (
                <article
                  key={`${r.id}-${i}`}
                  className="history-action-row"
                  onClick={() => navigate(`/equipment/${r.objet.id_objet}`)}
                >
                  <div className="history-action-left">
                    <div className="history-action-icon">
                      <i className={`fa-solid ${iconName}`} />
                    </div>
                    <div>
                      <div className="history-action-title">{t('history.equipmentReservation')}</div>
                      <div className="history-action-sub">{t('common.target')}: {r.objet.nom_model}</div>
                    </div>
                  </div>

                  <div className="history-action-right">
                    <span className="history-action-date"><i className="fa-regular fa-clock" /> {formatActionDate(r.date_reservation, t, locale)}</span>
                    <span className={`history-status ${statusClass(r.statut_reservation)}`}>
                      {translateData('reservationStatus', r.statut_reservation)}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>

          {actionsTotalPages > 1 && (
            <div className="pagination history-pagination">
              <button className="btn pagination-btn" disabled={actionsPage === 1} onClick={() => setActionsPage((p) => Math.max(1, p - 1))}>
                {t('common.previous')}
              </button>
              <span className="pagination-info">{t('common.page')} {actionsPage} / {actionsTotalPages}</span>
              <button className="btn pagination-btn" disabled={actionsPage === actionsTotalPages} onClick={() => setActionsPage((p) => Math.min(actionsTotalPages, p + 1))}>
                {t('common.next')}
              </button>
            </div>
          )}
        </section>

        <section className="history-panel card history-panel-gap">
          <div className="history-panel-head">
            <h2><i className="fa-solid fa-magnifying-glass" /> {t('history.searchHistory')}</h2>
          </div>
          <div className="history-panel-body">
            {history.length === 0 && <div className="history-empty">{t('history.noSearchHistory')}</div>}

            {pagedHistory.map((h, i) => (
              <article
                key={`${h.date_his}-${i}`}
                className="history-search-simple"
                onClick={() => navigate(`/search?q=${encodeURIComponent(h.requete_search)}`)}
              >
                <span className="history-query-text">{h.requete_search}</span>
                <span className="history-search-time">
                  <i className="fa-regular fa-clock" /> {formatRelativeTime(h.date_his, t, locale)}
                </span>
              </article>
            ))}
          </div>

          {searchTotalPages > 1 && (
            <div className="pagination history-pagination">
              <button className="btn pagination-btn" disabled={searchPage === 1} onClick={() => setSearchPage((p) => Math.max(1, p - 1))}>
                {t('common.previous')}
              </button>
              <span className="pagination-info">{t('common.page')} {searchPage} / {searchTotalPages}</span>
              <button className="btn pagination-btn" disabled={searchPage === searchTotalPages} onClick={() => setSearchPage((p) => Math.min(searchTotalPages, p + 1))}>
                {t('common.next')}
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
};

export default History;
