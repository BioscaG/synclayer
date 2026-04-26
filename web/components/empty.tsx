export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-soft p-12 text-center">
      <h3 className="display text-h3 mb-2">{title}</h3>
      {description && (
        <p className="text-body text-slate max-w-md mx-auto">{description}</p>
      )}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}
