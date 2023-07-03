//
// Copyright (c) 2022-2023 Antmicro
//
// This file is licensed under the Apache License 2.0.
// Full license text is available in 'LICENSE'.
//
using Microsoft.CodeAnalysis;

namespace ModelsAnalyzer;

public record struct RegisterEnumField(ISymbol RegisterSymbol, long RegisterAddress);
