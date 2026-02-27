import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const formatDistance = (value, t, locale) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return t('equipment.noDistance');
  if (n >= 1000) {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(n / 1000)} km`;
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Math.round(n))} m`;
};

const normalizeStatus = (status) => (status || '').toUpperCase();
const isAvailableStatus = (status) => String(status || '').toLowerCase().includes('disponible') || String(status || '').toLowerCase().includes('available');
const isBrokenStatus = (status) => {
  const lower = String(status || '').toLowerCase();
  return lower.includes('panne') || lower.includes('out of order') || lower.includes('aver');
};

const Equipment = () => {
  const { t, translateData, locale } = useI18n();
  const { id } = useParams();
  const navigate = useNavigate();

  const [equipment, setEquipment] = useState(null);
  const [queueInfo, setQueueInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState({ text: '', type: '' });

  const loadData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError('');

    try {
      const [detailsRes, queueRes] = await Promise.all([
        api.get(`/objects/${id}`),
        api.get(`/objects/${id}/queue`),
      ]);

      setEquipment(detailsRes.data || null);
      setQueueInfo(queueRes.data || null);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('equipment.notFoundTitle'));
      setEquipment(null);
      setQueueInfo(null);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    loadData(true);
  }, [id]);

  const reservationStatus = normalizeStatus(equipment?.my_reservation_status);

  const isMyReservationActive = reservationStatus === 'ACTIVE';
  const isMyReservationWaiting = reservationStatus === 'WAITING';
  const hasMyReservation = isMyReservationActive || isMyReservationWaiting;

  const waitingCount = useMemo(() => {
    const queueCount = Number(queueInfo?.waiting_count);
    if (Number.isFinite(queueCount)) return queueCount;

    const detailsCount = Number(equipment?.queue_count);
    if (Number.isFinite(detailsCount)) return detailsCount;

    return 0;
  }, [queueInfo, equipment]);

  const handleReserve = async () => {
    setActionLoading(true);
    setFeedback({ text: '', type: '' });

    try {
      const res = await api.post('/reservations', { object_id: Number(id) });
      setFeedback({ text: res.data?.message || t('equipment.reservationHandled'), type: 'success' });
      await loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : t('equipment.reserveError'), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelReservation = async () => {
    setActionLoading(true);
    setFeedback({ text: '', type: '' });

    try {
      let res;
      if (equipment?.my_reservation_id) {
        res = await api.delete(`/reservations/${equipment.my_reservation_id}`);
      } else {
        res = await api.delete(`/reservations?object_id=${id}`);
      }

      setFeedback({ text: res?.data?.message || t('equipment.cancelledSuccess'), type: 'success' });
      await loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : t('equipment.cancelError'), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCompleteReservation = async () => {
    setActionLoading(true);
    setFeedback({ text: '', type: '' });

    try {
      if (!equipment?.my_reservation_id) {
        setFeedback({ text: t('equipment.completeMissing'), type: 'error' });
        return;
      }

      const res = await api.post(`/reservations/${equipment.my_reservation_id}/complete`);
      setFeedback({ text: res.data?.message || t('equipment.completedSuccess'), type: 'success' });
      await loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : t('equipment.completeError'), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <main className="page-pad equipment-page">
        <div className="container">
          <div className="equip-loading card">
            <div className="equip-skeleton equip-skeleton-title" />
            <div className="equip-skeleton equip-skeleton-line" />
            <div className="equip-skeleton equip-skeleton-line short" />
            <div className="equip-skeleton equip-skeleton-box" />
          </div>
        </div>
      </main>
    );
  }

  if (error || !equipment) {
    return (
      <main className="page-pad equipment-page">
        <div className="container">
          <section className="card equip-error">
            <h2>{t('equipment.notFoundTitle')}</h2>
            <p>{error || t('equipment.notFoundBody')}</p>
            <button className="btn" onClick={() => navigate(-1)}>
              {t('equipment.back')}
            </button>
          </section>
        </div>
      </main>
    );
  }

  const localisation = equipment.localisation || {};
  const locationText = `${localisation.building || t('equipment.noBuilding')} - ${
    localisation.floor !== null && localisation.floor !== undefined ? `${t('common.floor')} ${localisation.floor}` : t('equipment.noFloor')
  } - ${localisation.room || t('equipment.noRoom')}`;

  const statusClass = isAvailableStatus(equipment.status) ? 'ok' : 'busy';

  return (
    <main className="page-pad equipment-page">
      <div className="container">
        <div className="equip-topbar">
          <button className="icon-btn" onClick={() => navigate(-1)}>
            <i className="fa-solid fa-arrow-left" />
          </button>
          <div>
            <h1 className="section-title">{t('equipment.title')}</h1>
            <p className="subtitle">{t('equipment.subtitle')}</p>
          </div>
        </div>

        <section className="card equip-hero-card">
          <div className="equip-hero-top">
            <div>
              <h2 className="equip-name">{equipment.name}</h2>
              <p className="equip-subtype">{translateData('type', equipment.type) || '-'} - {equipment.marque || '-'}</p>
            </div>
            <span className={`badge ${statusClass}`}>{translateData('status', equipment.status)}</span>
          </div>

          <div className="equip-meta-lines">
            <div className="equip-meta-line">
              <i className="fa-solid fa-location-dot" />
              <span>{locationText}</span>
            </div>
            <div className="equip-meta-line">
              <i className="fa-regular fa-compass" />
              <span>{formatDistance(equipment.distance_m, t, locale)}</span>
            </div>
          </div>
        </section>

        <section className="equip-details-grid">
          <article className="card equip-block">
            <h3>{t('common.features')}</h3>
            {Array.isArray(equipment.fonctionnalites) && equipment.fonctionnalites.length > 0 ? (
              <ul className="equip-list">
                {equipment.fonctionnalites.map((feature) => (
                  <li key={feature}>
                    <i className="fa-solid fa-check" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="equip-empty">{t('equipment.noFeatures')}</p>
            )}
          </article>

          <article className="card equip-block">
            <h3>{t('common.description')}</h3>
            <p className="equip-description">
              {equipment.description || t('equipment.noDescription')}
            </p>
          </article>

          <aside className="card equip-block equip-actions">
            <h3>{t('equipment.reservation')}</h3>

            {!hasMyReservation && (
              <button
                className="btn btn-primary equip-action-btn"
                onClick={handleReserve}
                disabled={actionLoading || isBrokenStatus(equipment.status)}
              >
                {isBrokenStatus(equipment.status)
                  ? t('equipment.unavailable')
                  : actionLoading
                  ? t('equipment.processing')
                  : t('equipment.reserve')}
              </button>
            )}

            {isMyReservationActive && (
              <button
                className="btn btn-primary equip-action-btn"
                onClick={handleCompleteReservation}
                disabled={actionLoading}
              >
                {actionLoading ? t('equipment.processing') : t('equipment.complete')}
              </button>
            )}

            {isMyReservationWaiting && (
              <button
                className="btn equip-action-btn"
                onClick={handleCancelReservation}
                disabled={actionLoading}
              >
                {actionLoading ? t('equipment.processing') : t('equipment.cancel')}
              </button>
            )}

            <div className="equip-queue">{t('equipment.queue')}: {waitingCount}</div>

            {isMyReservationWaiting && (
              <div className="chip chip-progress equip-chip">{t('equipment.waiting')}</div>
            )}

            {isMyReservationActive && (
              <div className="chip chip-done equip-chip">{t('equipment.active')}</div>
            )}

            {feedback.text && (
              <div className={`chip equip-chip ${feedback.type === 'error' ? 'chip-busy' : 'chip-done'}`}>
                {feedback.text}
              </div>
            )}
          </aside>
        </section>
      </div>
    </main>
  );
};

export default Equipment;
