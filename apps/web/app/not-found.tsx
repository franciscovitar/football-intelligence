import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page-shell not-found">
      <p className="eyebrow">404</p>
      <h1>No encontramos esa vista.</h1>
      <p>El jugador puede no existir en el scope activo o la ruta puede ser inválida.</p>
      <Link className="button button-primary" href="/rankings">
        Volver a rankings
      </Link>
    </main>
  );
}
