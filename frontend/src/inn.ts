export function normalizeInn(value: string): string {
  return value.replace(/\D/g, '').slice(0, 12);
}

export function isValidInn(value: string): boolean {
  if (!/^\d{10}$|^\d{12}$/.test(value)) {
    return false;
  }
  const digits = [...value].map(Number);
  const checksum = (part: number[], weights: number[]) =>
    part.reduce((sum, digit, index) => sum + digit * weights[index], 0) % 11 % 10;

  if (digits.length === 10) {
    return checksum(digits.slice(0, 9), [2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[9];
  }
  return (
    checksum(digits.slice(0, 10), [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[10] &&
    checksum(digits.slice(0, 11), [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[11]
  );
}
