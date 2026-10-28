// Minimized private task context. Never a source, role claim, or verified fact.
function approvedProfileContext(profile) {
  const result = {};
  const limits = { city: 100, purpose: 300, institution: 200, deadline: 10 };
  Object.keys(limits).forEach((key) => {
    const value = profile && profile[key];
    if (typeof value === "string" && value.trim()) {
      result[key] = Array.from(value.trim()).slice(0, limits[key]).join("");
    }
  });
  return result;
}
module.exports = { approvedProfileContext };
