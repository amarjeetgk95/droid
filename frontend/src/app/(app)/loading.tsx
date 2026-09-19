export default function AppLoading() {
  return (
    <div className="flex flex-col gap-3">
      <span className="skel block h-10 w-full" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[0, 1, 2, 3, 4].map((index) => (
          <span key={index} className="skel block h-44 w-full" />
        ))}
      </div>
      <span className="skel block h-56 w-full" />
    </div>
  );
}
