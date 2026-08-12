export function DataNotice({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <section className="data-notice" role="status">
      <div className="status-dot" aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
      </div>
    </section>
  );
}
