<?php
declare(strict_types=1);

namespace App\Models;

/**
 * Calculate the total price including tax.
 *
 * @param float $price    Base price
 * @param float $taxRate  Tax rate as decimal (e.g. 0.13)
 * @return float
 */
function calculateTotal(float $price, float $taxRate = 0.13): float
{
    return $price * (1 + $taxRate);
}

function formatCurrency(float $amount): string
{
    return '$' . number_format($amount, 2);
}

interface Renderable
{
    public function render(): string;
}

class Product implements Renderable
{
    private string $name;
    private float  $price;

    public function __construct(string $name, float $price)
    {
        $this->name  = $name;
        $this->price = $price;
    }

    public function getName(): string
    {
        return $this->name;
    }

    public function render(): string
    {
        return formatCurrency($this->price);
    }

    private function validate(): bool
    {
        return $this->price >= 0;
    }

    public static function fromArray(array $data): self
    {
        return new self($data['name'], $data['price']);
    }
}
