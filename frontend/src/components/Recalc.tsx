import { ChangesTable, FinishShift, Modal } from "./ui";
import type { RecalcResult } from "../types";

/** Shows what the deterministic engine recalculated after a planning edit. */
export function RecalcModal({ title, result, onClose, extra }: { title: string; result: RecalcResult; onClose: () => void; extra?: React.ReactNode }) {
  const moved = result.changes.filter((row) => row.finish_before !== row.finish_after).length;
  return (
    <Modal
      wide
      title={title}
      onClose={onClose}
      footer={
        <button className="btn dark" onClick={onClose}>
          Entendido
        </button>
      }
    >
      <div className="recalc-head">
        <div>
          <b>{result.changes.length}</b>
          <span>elementos recalculados</span>
        </div>
        <div>
          <b>{moved}</b>
          <span>cambian su término</span>
        </div>
        <div className="grow">
          <FinishShift before={result.finish_before} after={result.finish_after} />
        </div>
      </div>
      {extra}
      <ChangesTable changes={result.changes} />
      <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
        Fechas recalculadas con calendario laboral y feriados; costos, avance planificado, EVM y KPI se actualizaron a la fecha de corte.
      </p>
    </Modal>
  );
}
