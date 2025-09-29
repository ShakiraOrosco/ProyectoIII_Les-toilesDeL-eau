import React, { useEffect, useState } from "react";

function App() {
  const [reservas, setReservas] = useState([]);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/reservas/")
      .then(res => res.json())
      .then(data => setReservas(data));
  }, []);

  return (
    <div>
      <h1>Reservas Generales</h1>
      <ul>
        {reservas.map(r => <li key={r.id_reservas_gen}>Reserva {r.id_reservas_gen}</li>)}
      </ul>
    </div>
  );
}

export default App;
