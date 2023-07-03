//
// Copyright (c) 2022-2023 Antmicro
//
// This file is licensed under the Apache License 2.0.
// Full license text is available in 'LICENSE'.
//
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using System.Collections.Immutable;
using static ModelsAnalyzer.Rules;
using static ModelsAnalyzer.ContextualHelpers;

namespace ModelsAnalyzer;

[DiagnosticAnalyzer(LanguageNames.CSharp)]
public class RegistersEnumAnalyzer : DiagnosticAnalyzer, IAnalyzerWithStatus
{
    public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
        => ImmutableArray.Create(RuleNoExplicitMemberValue, RuleNotLongUnderlyingType, RuleNoRegistersEnum);

    public ProtectedAnalyzerStatus AnalyzerStatus { get; } = new();

    private class RegistersEnumAnalyzerInternalStateful
    {
        private volatile int registersCtr = 0;
        public void GetRegistersAndValues(SyntaxNodeAnalysisContext context)
        {
            if(!CanBeRegistersEnum((EnumDeclarationSyntax)context.Node))
            {
                return;
            }

            RegistersEnumAnalyzer.GetRegistersAndValues((EnumDeclarationSyntax)context.Node, context.SemanticModel, context);
            Interlocked.Increment(ref registersCtr);
        }

        public void EndAnalysis(SymbolAnalysisContext context)
        {
            if(registersCtr > 0)
            {
                return;
            }

            // highlight class name
            foreach(var location in context.Symbol.Locations)
            {
                context.ReportDiagnostic(
                    Diagnostic.Create(RuleNoRegistersEnum, location)
                );
            }
        }
    }

    public static IList<RegisterEnumField> GetRegistersAndValues(EnumDeclarationSyntax registers, SemanticModel SemanticModel, SyntaxNodeAnalysisContext? context = null)
    {
        if(SemanticModel.GetDeclaredSymbol(registers) is not INamedTypeSymbol enumSymbol)
        {
            throw new InvalidDataException("Enum Syntax Node does not resolve to INamedTypeSymbol Symbol. This is serious and unexpected - check if the project is compiled without errors.");
        }
        var longTypeBuiltin = SemanticModel.Compilation.GetSpecialType(SpecialType.System_Int64);

        // this is guaranteed to be an enum at this point
        if(enumSymbol.EnumUnderlyingType!.SpecialType != longTypeBuiltin.SpecialType)
        {
            context?.ReportDiagnostic(
                Diagnostic.Create(RuleNotLongUnderlyingType, registers.GetNameToken().GetLocation(), registers.Identifier.Text)
            );
        }

        var rets = new List<RegisterEnumField>();
        long prev = -1;
        foreach(var e in registers.Members)
        {
            var symbol = SemanticModel.GetDeclaredSymbol(e);
            if(symbol is null)
            {
                throw new InvalidDataException("Enum member cannot be resolved to symbol. This can signify a problem with project's compilation - check if the project is compiled without errors.");
            }

            long constVal = ++prev;
            if(e.EqualsValue is not null)
            {
                constVal = (long)Convert.ChangeType(SemanticModel.GetConstantValue(e.EqualsValue.Value).Value!, typeof(long));
            }
            else
            {
                context?.ReportDiagnostic(
                    Diagnostic.Create(RuleNoExplicitMemberValue, e.GetLocation(), symbol.Name, constVal)
                );
            }

            rets.Add(new(symbol, constVal));
            prev = constVal;
        }
        return rets;
    }

    public override void Initialize(AnalysisContext context)
    {
        context.EnableConcurrentExecution();
        context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.Analyze | GeneratedCodeAnalysisFlags.ReportDiagnostics);

        var analyzerInternal = new RegistersEnumAnalyzerInternalStateful();

        context.RegisterSymbolStartAction(ctx =>
        {
            ctx.RegisterSyntaxNodeAction(analyzerInternal.GetRegistersAndValues, SyntaxKind.EnumDeclaration);

            if(ctx.Symbol is INamedTypeSymbol ns && IsClassAPeripheral(ns))
            {
                ctx.RegisterSymbolEndAction(analyzerInternal.EndAnalysis);
            }

            AnalyzerStatus.Pass();
        }, SymbolKind.NamedType);
    }
}

public static class RegisterEnumAnalyzerHelper
{
    public static ImmutableArray<RegisterEnumField> FindRegistersSymbols(SemanticModel model)
    {
        List<RegisterEnumField> enumMemberSymbols = new();

        var cls = GetAllPeripheralClasses(model);
        foreach(var cl in cls)
        {
            var enums = cl.Item1.DescendantNodes().OfType<EnumDeclarationSyntax>();
            foreach(var enumDecl in enums)
            {
                if(!CanBeRegistersEnum(enumDecl))
                {
                    continue;
                }

                var list = RegistersEnumAnalyzer.GetRegistersAndValues(enumDecl, model);
                enumMemberSymbols.AddRange(list.ToArray());
            }
        }

        return enumMemberSymbols.ToImmutableArray();
    }
}
